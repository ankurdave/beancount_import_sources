"""Cash App CSV source.

To download a CSV, go to https://cash.app/account/activity and click Statements
-> Export CSV.

Example usage:

    data_dir = os.path.dirname(__file__)
    data_sources = [
        dict(
            module='beancount_import_sources.cashapp_csv_source',
            cashapp_account='Assets:CashApp',
            data_dir=data_dir,
            csv_filenames=glob.glob(os.path.join(data_dir, 'data/CashApp/*.csv'))
        ),
    ]
    beancount_import.webserver.main(data_sources=data_sources, ...)

"""

from typing import List, Optional, Tuple, Dict, Set
import datetime
import os
import collections
import functools
import re
import csv
from collections import Counter
from beancount.core.amount import mul
from beancount.core.number import D, ZERO, Decimal
from beancount.core.data import Open, Transaction, Posting, Amount, Entries, Directive, EMPTY_SET
from beancount_import.source import ImportResult, SourceResults, Source, AssociatedData, InvalidSourceReference
from beancount_import.matching import FIXME_ACCOUNT


class Config(object):
    def __init__(self, cashapp_account, **kwargs):
        super().__init__(**kwargs)
        self.cashapp_account = cashapp_account


class CashAppCsvSource(Config, Source):
    def __init__(self, data_dir: str, csv_filenames: List[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir = data_dir
        self.csv_filenames = sorted([os.path.realpath(x) for x in csv_filenames])
        self.example_posting_key_extractors = {
            'cashapp_payee': None,
            'cashapp_description': None,
        }

    @property
    def name(self):
        return 'cashapp_csv'

    def sanitize(self, string: str) -> str:
        # Remove all non-ASCII and non-printable ASCII characters, including newlines.
        return re.sub(r'[^ -~]+', '', string)

    def record_transaction(self, txn_id, txn: Transaction, results: SourceResults):
        self.imported_transactions_by_id.setdefault(txn_id, []).append(txn)
        if txn_id not in self.existing_transactions_by_id:
            results.add_pending_entry(ImportResult(date=txn.date, entries=[txn], info=None))

    def make_payment_transaction(self, txn_id, date, txn_type, payee, notes, amount, results: SourceResults):
        txn = Transaction(
            meta={},
            date=date,
            flag='*',
            payee=payee,
            narration='CashApp payment: ' + self.sanitize(notes),
            tags=EMPTY_SET,
            links=EMPTY_SET,
            postings=[])
        txn.postings.append(
            Posting(
                account=self.cashapp_account,
                units=amount,
                cost=None,
                meta={
                    'date': date,
                    'cashapp_transaction_id': txn_id,
                    'cashapp_payee': payee,
                    'cashapp_type': txn_type,
                    'cashapp_description': self.sanitize(notes),
                },
                price=None,
                flag=None))
        txn.postings.append(
            Posting(
                account=FIXME_ACCOUNT,
                units=-amount,
                cost=None,
                meta={},
                price=None,
                flag=None))
        self.record_transaction(txn_id, txn, results)

    def make_transfer_transaction(self, txn_id, date, transfer_to: str, amount,
                                  results: SourceResults, for_payment_notes=None, for_payee=None):
        txn = Transaction(
            meta={},
            date=date,
            flag='*',
            payee='',
            narration='CashApp transfer to/from ' + transfer_to,
            tags=EMPTY_SET,
            links=EMPTY_SET,
            postings=[])
        meta = {
            'date': date,
            'cashapp_transaction_id': txn_id,
            'cashapp_type': 'transfer',
        }
        if for_payment_notes is not None and for_payee is not None:
            meta['cashapp_payee'] = self.sanitize(for_payee)
            meta['cashapp_description'] = self.sanitize(for_payment_notes)
        txn.postings.append(
            Posting(
                account=self.cashapp_account,
                units=amount,
                cost=None,
                meta=meta,
                price=None,
                flag=None))
        txn.postings.append(
            Posting(
                account=FIXME_ACCOUNT,
                units=-amount,
                cost=None,
                meta={},
                price=None,
                flag=None))
        self.record_transaction(txn_id, txn, results)

    def prepare(self, journal, results: SourceResults):
        results.add_account(self.cashapp_account)

        # Scan the journal to see which transactions we have already imported.
        self.existing_transactions_by_id = dict()
        for transaction in journal.all_entries:
            if not isinstance(transaction, Transaction): continue
            for posting in transaction.postings:
                meta = posting.meta
                if (meta and 'cashapp_transaction_id' in meta):
                    txn_id = meta['cashapp_transaction_id']
                    self.existing_transactions_by_id.setdefault(txn_id, []).append(transaction)

        # Read all files and add pending transactions not already imported into the journal.
        self.imported_transactions_by_id = dict()
        for filename in self.csv_filenames:
            self.log_status('cashapp_csv: processing %s' % (filename, ))
            with open(filename) as f:
                rows = list(csv.reader(f))[1:]
            for row in rows:
                txn_id = row[0]
                date = datetime.datetime.strptime(row[1][:-4], '%Y-%m-%d %H:%M:%S').date()
                txn_type = row[2]
                amount = Amount(currency=row[3], number=Decimal(row[4].replace('$', '')))
                fee = row[5]
                assert fee == '$0'
                notes = row[11]
                payee = row[12]
                account = row[13]

                if txn_type == 'Received P2P' or txn_type == 'Sent P2P':
                    if account != 'Your Cash':
                        # The outgoing payment is funded by an incoming transfer, or the incoming
                        # payment is directly transferred.
                        self.make_transfer_transaction(
                            txn_id=txn_id,
                            date=date,
                            transfer_to=account,
                            amount=-amount,
                            results=results,
                            for_payment_notes=notes,
                            for_payee=payee)

                    self.make_payment_transaction(txn_id=txn_id,
                                                  date=date,
                                                  txn_type=txn_type,
                                                  payee=payee,
                                                  notes=notes,
                                                  amount=amount,
                                                  results=results)

                elif txn_type == 'Cash out':
                    self.make_transfer_transaction(
                        txn_id=txn_id,
                        date=date,
                        transfer_to='bank',
                        amount=amount,
                        results=results)
                else:
                    assert False, txn_type


        # Report transactions in the journal that do not have a corresponding transaction in the
        # source files. A given transaction id may result in multiple ledger transactions, so we
        # check that the number of transactions matches.
        for txn_id, transactions in self.existing_transactions_by_id.items():
            num_expected = len(self.imported_transactions_by_id.get(txn_id, []))
            if len(transactions) == num_expected: continue
            num_extra = len(transactions) - num_expected
            results.add_invalid_reference(
                InvalidSourceReference(num_extra,
                                       [(transaction, None) for transaction in transactions]))

    def is_posting_cleared(self, posting: Posting):
        return 'cashapp_transaction_id' in posting.meta

def load(spec, log_status):
    return CashAppCsvSource(log_status=log_status, **spec)
