"""Venmo JSON source.

To download a JSON file containing your transaction history:

1. Sign in to Venmo (https://venmo.com/account/sign-in).

2. Obtain your user id. It is available at https://api.venmo.com/v1/me, under
   the response.data.user.id field.

3. Go to https://api.venmo.com/v1/transaction-history?start_date=2022-01-01&end_date=2022-12-31&profile_id=<YOUR_USER_ID>&account_type=personal

Example usage:

    data_dir = os.path.dirname(__file__)
    data_sources = [
        dict(
            module='beancount_import_sources.venmo_json_source',
            data_dir=data_dir,
            self_username='John-Doe',
            venmo_assets_account='Assets:Venmo',
            json_filenames=glob.glob(os.path.join(data_dir, 'data/Venmo/*.json')),
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
import json
from collections import Counter
from beancount.core.number import D, ZERO, Decimal
from beancount.core.data import Open, Transaction, Posting, Amount, Entries, Directive, EMPTY_SET
from beancount_import.source import ImportResult, SourceResults, Source, AssociatedData, InvalidSourceReference
from beancount_import.matching import FIXME_ACCOUNT


class Config(object):
    def __init__(self,
                 self_username: str,
                 venmo_assets_account: str,
                 **kwargs):
        super().__init__(**kwargs)
        self.self_username = self_username
        self.venmo_assets_account = venmo_assets_account


class VenmoJsonSource(Config, Source):
    def __init__(self, data_dir: str, json_filenames: List[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir = data_dir
        self.json_filenames = sorted([os.path.realpath(x) for x in json_filenames])
        self.example_posting_key_extractors = {
            'venmo_payee': None,
            'venmo_description': None,
        }

    @property
    def name(self):
        return 'venmo_json'

    def to_amount(self, json_amount: Decimal) -> Amount:
        return Amount(currency='USD', number=json_amount)

    def sanitize(self, string: str) -> str:
        # Remove all non-ASCII and non-printable ASCII characters, including newlines.
        return re.sub(r'[^ -~]+', '', string)

    def record_transaction(self, transaction, txn: Transaction, results: SourceResults):
        self.imported_transactions_by_id.setdefault(transaction['id'], []).append(txn)
        if transaction['id'] not in self.existing_transactions_by_id:
            results.add_pending_entry(ImportResult(date=txn.date, entries=[txn], info=None))

    def make_payment_transaction(self, transaction, payment, payee, amount_coef, results: SourceResults):
        txn = Transaction(
            meta={},
            date=self.get_transaction_date(transaction),
            flag='*',
            payee=self.get_user_info(payee, 'display_name'),
            narration='Venmo ' + transaction['type'] + ': ' + self.sanitize(payment['note']),
            tags=EMPTY_SET,
            links=EMPTY_SET,
            postings=[])
        txn.postings.append(
            Posting(
                account=self.venmo_assets_account,
                units=self.to_amount(amount_coef * payment['amount']),
                cost=None,
                meta={
                    'venmo_transaction_id': transaction['id'],
                    'venmo_payee': self.get_user_info(payee, 'username', 'display_name'),
                    'venmo_type': payment['action'],
                    'venmo_description': self.sanitize(payment['note']),
                },
                price=None,
                flag=None))
        txn.postings.append(
            Posting(
                account=FIXME_ACCOUNT,
                units=self.to_amount(-amount_coef * payment['amount']),
                cost=None,
                meta={},
                price=None,
                flag=None))
        self.record_transaction(transaction, txn, results)

    def make_transfer_transaction(self, transaction, transfer_to: str, amount_coef,
                                  results: SourceResults, for_payment=None, for_payee=None):
        txn = Transaction(
            meta={},
            date=self.get_transaction_date(transaction),
            flag='*',
            payee='',
            narration='Venmo transfer to ' + transfer_to,
            tags=EMPTY_SET,
            links=EMPTY_SET,
            postings=[])
        meta = {
            'venmo_transaction_id': transaction['id'],
            'venmo_type': 'transfer',
        }
        if for_payment is not None and for_payee is not None:
            meta['venmo_payee'] = self.get_user_info(for_payee, 'username', 'display_name')
            meta['venmo_description'] = self.sanitize(for_payment['note'])
        txn.postings.append(
            Posting(
                account=self.venmo_assets_account,
                units=self.to_amount(amount_coef * transaction['amount']),
                cost=None,
                meta=meta,
                price=None,
                flag=None))
        txn.postings.append(
            Posting(
                account=FIXME_ACCOUNT,
                units=self.to_amount(-amount_coef * transaction['amount']),
                cost=None,
                meta={},
                price=None,
                flag=None))
        self.record_transaction(transaction, txn, results)

    def get_user_info(self, actor, *attrs):
        if 'user' in actor:
            d = actor['user']
        else:
            d = actor
        for attr in attrs:
            if attr in d and d[attr] is not None:
                return d[attr]
        return '(unknown)'

    def get_transaction_date(self, transaction) -> datetime.date:
        return datetime.datetime.strptime(transaction['datetime_created'], '%Y-%m-%dT%H:%M:%S').date()

    def prepare(self, journal, results: SourceResults):
        results.add_account(self.venmo_assets_account)

        # Scan the journal to see which transactions we have already imported.
        self.existing_transactions_by_id = dict()
        for transaction in journal.all_entries:
            if not isinstance(transaction, Transaction): continue
            for posting in transaction.postings:
                meta = posting.meta
                if (meta and 'venmo_transaction_id' in meta):
                    txn_id = meta['venmo_transaction_id']
                    self.existing_transactions_by_id.setdefault(txn_id, []).append(transaction)

        # Read all files and add pending transactions not already imported into the journal.
        self.imported_transactions_by_id = dict()
        for filename in self.json_filenames:
            self.log_status('venmo_json: processing %s' % (filename, ))
            with open(filename) as f:
                data = json.load(f, parse_float=Decimal)
            for transaction in data['data']['transactions']:
                txn_id = transaction['id']
                txn_type = transaction['type']
                if txn_type == 'payment' or txn_type == 'refund':
                    if txn_type == 'payment':
                        payment = transaction['payment']
                    elif txn_type == 'refund':
                        # A refund has a nested payment object that contains the
                        # transaction that was reversed.
                        payment = transaction['refund']['payment']
                    else:
                        assert False, txn_type
                    actor_username = self.get_user_info(payment['actor'], 'username')
                    target_username = self.get_user_info(payment['target'], 'username')
                    if target_username == self.self_username:
                        payee = payment['actor']
                        if payment['action'] == 'pay':
                            # Someone is paying us.
                            amount_coef = 1
                        elif payment['action'] == 'charge':
                            # Someone is charging us.
                            amount_coef = -1
                        else:
                            assert False
                    elif actor_username == self.self_username:
                        payee = payment['target']
                        if payment['action'] == 'pay':
                            # We are paying someone.
                            amount_coef = -1
                        elif payment['action'] == 'charge':
                            # We are charging someone.
                            amount_coef = 1
                        else:
                            assert False

                    if txn_type == 'refund':
                        # The payment contains the transaction that was
                        # reversed. Flip the amount to produce a transaction
                        # that will achieve the refund.
                        amount_coef *= -1

                    # The outgoing payment is funded by an incoming transfer, or
                    # the incoming payment is directly transferred.
                    if (transaction['funding_source']
                        and transaction['funding_source']['type'] in ['bank', 'transfer']):
                        self.make_transfer_transaction(
                            transaction=transaction,
                            transfer_to=transaction['funding_source']['name'],
                            amount_coef=-amount_coef, results=results,
                            for_payment=payment, for_payee=payee)

                    self.make_payment_transaction(transaction=transaction,
                                                  payment=payment, payee=payee,
                                                  amount_coef=amount_coef, results=results)

                elif txn_type == 'transfer':
                    # Transfer from Venmo to bank.
                    transfer = transaction[txn_type]
                    destination_name = transfer['destination']['name']
                    self.make_transfer_transaction(transaction=transaction, transfer_to=destination_name,
                                                   amount_coef=-1, results=results)
                elif txn_type == 'disbursement':
                    # Payment from some merchant to us.
                    disbursement = transaction[txn_type]
                    payee = disbursement['merchant']
                    payment = {
                        'note': transaction['note'],
                        'amount': transaction['amount'],
                        'action': 'disbursement',
                    }
                    self.make_payment_transaction(transaction=transaction,
                                                  payment=payment, payee=payee,
                                                  amount_coef=1, results=results)
                else:
                    assert False, txn_type


        # Report transactions in the journal that do not have a corresponding
        # transaction in the source files. A given Venmo transaction id may
        # result in multiple ledger transactions, so we check that the number of
        # transactions matches.
        for txn_id, transactions in self.existing_transactions_by_id.items():
            num_expected = len(self.imported_transactions_by_id.get(txn_id, []))
            if len(transactions) == num_expected: continue
            num_extra = len(transactions) - num_expected
            results.add_invalid_reference(
                InvalidSourceReference(num_extra,
                                       [(transaction, None) for transaction in transactions]))

    def is_posting_cleared(self, posting: Posting):
        return 'venmo_transaction_id' in posting.meta

def load(spec, log_status):
    return VenmoJsonSource(log_status=log_status, **spec)
