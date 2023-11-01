"""Source for Emburse Chrome River reimbursements in CSV format.

Emburse Chrome River exposes this data in XLSX format at Inquiry > Expense > My
Expense Items > Export. You must convert them to CSV format manually.

Emburse Chrome River groups expense items into expense reports. This source
creates one transaction for each expense report. The transaction indicates that
previously-incurred expenses are actually receivables. Therefore the transaction
contains two postings for each expense item: one that subtracts the amount from
the expense account (listed as Expenses:FIXME to allow selecting the appropriate
expense account), and one that adds the amount to the assets-receivable account
specified in the `receivable_account` config parameter.

Example usage:

    data_dir = os.path.dirname(__file__)
    data_sources = [
        dict(
            module='beancount_import_sources.emburse_chrome_river_source',
            data_dir=data_dir,
            csv_filenames=glob.glob(os.path.join(data_dir, 'data/Hooli/Emburse/*.csv')),
            receivable_account='Assets:Receivable:Hooli',
            company_name='Hooli',
        ),
    ]
    beancount_import.webserver.main(data_sources=data_sources, ...)

"""

from typing import List, Optional, Tuple, Dict, Set, NamedTuple
import datetime
import os
import collections
import functools
import re
import csv
import pandas as pd
from collections import Counter
from beancount.core.amount import mul
from beancount.core.number import D, ZERO, Decimal
from beancount.core.data import Open, Transaction, Posting, Amount, Entries, Directive, EMPTY_SET
from beancount_import.source import ImportResult, SourceResults, Source, AssociatedData, InvalidSourceReference
from beancount_import.matching import FIXME_ACCOUNT


class Config(object):
    def __init__(self, receivable_account, company_name, **kwargs):
        super().__init__(**kwargs)
        self.receivable_account = receivable_account
        self.company_name = company_name


class EmburseChromeRiverSource(Config, Source):
    def __init__(self, data_dir: str, csv_filenames: List[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir = data_dir
        self.csv_filenames = sorted([os.path.realpath(x) for x in csv_filenames])
        self.example_posting_key_extractors = {
            'emburse_chrome_river_expense_type': None,
            'emburse_chrome_river_business_purpose': None}

    @property
    def name(self):
        return 'emburse_chrome_river'

    def _to_amount(self, s: str) -> Amount:
        if s == '--':
            number = ZERO
        else:
            number = Decimal(s.replace('$', '').replace(',', '').strip())
        return Amount(currency='USD', number=number)

    def prepare(self, journal, results: SourceResults):
        # Scan the journal to see which transactions we have already imported.
        # Transactions are identified by report id.
        existing_transactions_by_report_id = dict()
        for transaction in journal.all_entries:
            if not isinstance(transaction, Transaction): continue
            meta = transaction.meta
            if meta is not None and 'emburse_chrome_river_report_id' in meta:
                key = transaction.meta['emburse_chrome_river_report_id']
                existing_transactions_by_report_id.setdefault(key, []).append(transaction)

        # Read all files and add pending entries not already imported into the journal.
        imported_transactions_by_report_id = dict()
        for filename in self.csv_filenames:
            self.log_status('emburse_chrome_river: processing %s' % (filename, ))
            with open(filename) as f:
                rows = list(csv.reader(f))[1:-2]
            relative_filename = os.path.relpath(filename, start=self.data_dir)

            # Group expense items by report id.
            ExpenseItem = NamedTuple('ExpenseItem', [
                ('report_name', str),
                ('transaction_date', datetime.date),
                ('expense_type', str),
                ('amount', Amount),
                ('approval_date', datetime.date),
                ('business_purpose', str),
                ('report_id', str)])
            expense_items_by_report_id = dict()
            for row in rows:
                expense_item = ExpenseItem(
                    report_name = row[0],
                    transaction_date = datetime.datetime.strptime(row[1], '%m/%d/%y').date(),
                    expense_type = row[2],
                    amount = Amount(currency=row[9], number=Decimal(row[8])),
                    approval_date = datetime.datetime.strptime(row[10], '%m/%d/%y').date(),
                    business_purpose = row[11],
                    report_id = row[12])
                expense_items_by_report_id.setdefault(expense_item.report_id, []).append(expense_item)

            for report_id, expense_items in expense_items_by_report_id.items():
                txn = Transaction(
                    meta=collections.OrderedDict(),
                    date=expense_items[0].approval_date,
                    flag='*',
                    payee=self.company_name,
                    narration=f'Expense report: {expense_items[0].report_name}',
                    tags=EMPTY_SET,
                    links=EMPTY_SET,
                    postings=[])
                txn.meta['emburse_chrome_river_source_file'] = relative_filename
                txn.meta['emburse_chrome_river_report_id'] = expense_items[0].report_id
                txn.meta['emburse_chrome_river_report_name'] = expense_items[0].report_name

                for expense_item in expense_items:
                    txn.postings.append(Posting(
                        account='Expenses:FIXME',
                        # The original expense turned out to be reimbursable, so
                        # we account for it here as a negative expense to cancel
                        # out the original expense.
                        units=-expense_item.amount,
                        cost=None,
                        price=None,
                        flag=None,
                        meta={
                            'emburse_chrome_river_expense_type': expense_item.expense_type,
                            'emburse_chrome_river_business_purpose': expense_item.business_purpose,
                            'emburse_chrome_river_transaction_date': expense_item.transaction_date,
                        }))
                    txn.postings.append(Posting(
                        account=self.receivable_account,
                        units=expense_item.amount,
                        cost=None,
                        price=None,
                        flag=None,
                        meta={}))

                imported_transactions_by_report_id.setdefault(report_id, []).append(txn)
                if report_id not in existing_transactions_by_report_id:
                    results.add_pending_entry(ImportResult(date=txn.date, entries=[txn], info=None))

        # Report transactions in the journal that have metadata that should
        # associate them with a source file, but that source file is not found.
        for report_id, transactions in existing_transactions_by_report_id.items():
            num_expected = len(imported_transactions_by_report_id.get(report_id, []))
            if len(transactions) == num_expected: continue
            num_extra = len(transactions) - num_expected
            results.add_invalid_reference(
                InvalidSourceReference(num_extra,
                                       [(transaction, None) for transaction in transactions]))

    def is_posting_cleared(self, posting: Posting):
        raise NotImplementedError

def load(spec, log_status):
    return EmburseChromeRiverSource(log_status=log_status, **spec)
