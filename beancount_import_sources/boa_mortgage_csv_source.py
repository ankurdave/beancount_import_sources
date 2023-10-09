"""Bank of America mortgage statement CSV source.
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
    def __init__(self, payment_account, loan_balance_account, interest_account,
                 escrow_account, fees_account, **kwargs):
        super().__init__(**kwargs)
        self.payment_account = payment_account
        self.loan_balance_account = loan_balance_account
        self.interest_account = interest_account
        self.escrow_account = escrow_account
        self.fees_account = fees_account


class BoAMortgageCsvSource(Config, Source):
    def __init__(self, data_dir: str, csv_filenames: List[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir = data_dir
        self.csv_filenames = sorted([os.path.realpath(x) for x in csv_filenames])
        self.example_posting_key_extractors = {}

    @property
    def name(self):
        return 'boa_mortgage_csv'

    def _to_amount(self, s: str) -> Amount:
        if s == '--':
            number = ZERO
        else:
            number = Decimal(s.replace('$', '').replace(',', '').strip())
        return Amount(currency='USD', number=number)

    def _get_transaction_key(self, txn: Transaction):
        filename = txn.meta['boa_mortgage_csv_source_file']
        description = txn.meta['boa_mortgage_csv_source_description']
        return (filename, txn.date, description)

    def prepare(self, journal, results: SourceResults):
        # This source is not authoritative for the payment account because it
        # will likely be referenced in mortgage payment transactions that appear
        # in bank account statements.
        results.add_account(self.loan_balance_account)
        results.add_account(self.interest_account)
        results.add_account(self.escrow_account)
        results.add_account(self.fees_account)

        # Scan the journal to see which transactions we have already imported.
        # Transactions are identified by file, date, and description.
        existing_transactions_by_file_date_desc = dict()
        for transaction in journal.all_entries:
            if not isinstance(transaction, Transaction): continue
            meta = transaction.meta
            if meta is not None and 'boa_mortgage_csv_source_file' in meta:
                key = self._get_transaction_key(transaction)
                existing_transactions_by_file_date_desc.setdefault(key, []).append(transaction)

        # Read all files and add pending entries not already imported into the journal.
        imported_transactions_by_file_date_desc = dict()
        for filename in self.csv_filenames:
            self.log_status('boa_mortgage_csv: processing %s' % (filename, ))
            with open(filename) as f:
                rows = list(csv.reader(f))[1:]
            relative_filename = os.path.relpath(filename, start=self.data_dir)
            for row in rows:
                date = datetime.datetime.strptime(row[0], '%m/%d/%y').date()
                description = row[1]
                txn_type = row[2]
                payment_amount = self._to_amount(row[3])
                principal_amount = self._to_amount(row[5])
                interest_amount = self._to_amount(row[6])
                escrow_amount = self._to_amount(row[7])
                fees_amount = self._to_amount(row[8])

                txn = Transaction(
                    meta=collections.OrderedDict(),
                    date=date,
                    flag='*',
                    payee='Bank of America',
                    narration=description,
                    tags=EMPTY_SET,
                    links=EMPTY_SET,
                    postings=[])
                txn.meta['boa_mortgage_csv_source_file'] = relative_filename
                txn.meta['boa_mortgage_csv_source_description'] = description

                txn.postings.append(Posting(
                    account=self.payment_account,
                    units=-payment_amount,
                    cost=None,
                    price=None,
                    flag=None,
                    meta={'boa_mortgage_csv_source_file': relative_filename}))
                if principal_amount:
                    txn.postings.append(Posting(
                        account=self.loan_balance_account,
                        units=principal_amount,
                        cost=None,
                        price=None,
                        flag=None,
                        meta={'boa_mortgage_csv_source_file': relative_filename}))
                if interest_amount:
                    txn.postings.append(Posting(
                        account=self.interest_account,
                        units=interest_amount,
                        cost=None,
                        price=None,
                        flag=None,
                        meta={'boa_mortgage_csv_source_file': relative_filename}))
                if escrow_amount:
                    txn.postings.append(Posting(
                        account=self.escrow_account,
                        units=escrow_amount,
                        cost=None,
                        price=None,
                        flag=None,
                        meta={'boa_mortgage_csv_source_file': relative_filename}))
                if fees_amount:
                    txn.postings.append(Posting(
                        account=self.fees_account,
                        units=fees_amount,
                        cost=None,
                        price=None,
                        flag=None,
                        meta={'boa_mortgage_csv_source_file': relative_filename}))

                key = self._get_transaction_key(txn)
                imported_transactions_by_file_date_desc.setdefault(key, []).append(txn)
                if key not in existing_transactions_by_file_date_desc:
                    results.add_pending_entry(ImportResult(date=txn.date, entries=[txn], info=None))


        # Report transactions in the journal that have metadata that should
        # associate them with a source file, but that source file is not found.
        for key, transactions in existing_transactions_by_file_date_desc.items():
            num_expected = len(imported_transactions_by_file_date_desc.get(key, []))
            if len(transactions) == num_expected: continue
            num_extra = len(transactions) - num_expected
            results.add_invalid_reference(
                InvalidSourceReference(num_extra,
                                       [(transaction, None) for transaction in transactions]))

    def is_posting_cleared(self, posting: Posting):
        return posting.meta is not None and 'boa_mortgage_csv_source_file' in posting.meta

def load(spec, log_status):
    return BoAMortgageCsvSource(log_status=log_status, **spec)
