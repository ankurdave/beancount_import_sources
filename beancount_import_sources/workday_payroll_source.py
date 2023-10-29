from typing import List, Optional, Tuple, Dict, Set
import glob
import datetime
import os
import collections
import functools
import re
import json
import warnings
import openpyxl
from .multitable_reader import MultiTableReader
from collections import Counter
from beancount.core.number import D, ZERO, Decimal
from beancount.core.data import Open, Transaction, Posting, Amount, Entries, Directive, EMPTY_SET
from beancount_import.source import ImportResult, SourceResults, Source, AssociatedData, InvalidSourceReference
from beancount_import.matching import FIXME_ACCOUNT
import numpy as np


class Config(object):
    def __init__(self, company_name, item_date_to_account_by_section, **kwargs):
        super().__init__(**kwargs)
        self.company_name = company_name
        self.item_date_to_account_by_section = item_date_to_account_by_section


class WorkdayPayrollSource(Config, Source):
    def __init__(self, data_dir: str, xlsx_dir: str,
                 authoritative_accounts: List[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir = data_dir
        self.xlsx_dir = xlsx_dir
        self.xlsx_filenames = sorted([
            os.path.realpath(x)
            for x in glob.glob(os.path.join(os.path.join(data_dir, xlsx_dir), '*.xlsx'))
        ])
        self.authoritative_accounts = authoritative_accounts
        self.example_posting_key_extractors = {'workday_payroll_posting_description': None}

    @property
    def name(self):
        return 'workday_payroll'

    def _to_amount(self, amount, account, currency) -> Amount:
        if np.isnan(amount): return None
        if amount > 0 and any(account.startswith(prefix)
                              for prefix in ['Income:', 'Equity:', 'Liabilities:']):
            amount *= -1
        if amount < 0 and any(account.startswith(prefix)
                              for prefix in ['Expenses:', 'Assets:']):
            amount *= -1
        return Amount(currency='USD', number=round(Decimal(amount), 2))

    def prepare(self, journal, results: SourceResults):
        for account in self.authoritative_accounts:
            results.add_account(account)

        # Scan the journal to see which files we have already imported.
        existing_transactions_by_file = dict()
        for transaction in journal.all_entries:
            if not isinstance(transaction, Transaction): continue
            meta = transaction.meta
            if (meta and 'workday_payroll_source_file' in meta):
                filename = meta['workday_payroll_source_file']
                if not filename.startswith(self.xlsx_dir):
                    # Ignore files outside the relevant directory. This allows
                    # this source to be used multiple times with different
                    # configurations.
                    continue
                existing_transactions_by_file.setdefault(filename, []).append(transaction)

        # Read all files and add pending entries not already imported into the journal.
        imported_transactions_by_file = dict()
        for filename in self.xlsx_filenames:
            self.log_status('workday_payroll: processing %s' % (filename, ))

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                wb = openpyxl.load_workbook(filename)
                sh = wb.worksheets[0]

            rows = [[cell.value for cell in r] for r in sh.rows]
            tables_by_name = MultiTableReader().read_tables(rows)

            date_str = tables_by_name['Payslip Information']['Check Date'][0]
            date = datetime.datetime.strptime(date_str, '%m/%d/%Y').date()

            txn = Transaction(
                meta=collections.OrderedDict(),
                date=date,
                flag='*',
                payee=self.company_name,
                narration='Payroll',
                tags=EMPTY_SET,
                links=EMPTY_SET,
                postings=[])
            relative_filename = os.path.relpath(filename, start=self.data_dir)
            txn.meta['workday_payroll_source_file'] = relative_filename

            for section_name, table in tables_by_name.items():
                if section_name not in self.item_date_to_account_by_section: continue
                item_date_to_account = self.item_date_to_account_by_section[section_name]
                for i, row in table.iterrows():
                    accounts = item_date_to_account(row.iloc[0], date)
                    if isinstance(accounts, str):
                        accounts = [accounts]
                    for account in accounts:
                        if 'Amount' in row:
                            amount = self._to_amount(row['Amount'], account, 'USD')
                        elif 'Amount in Pay Group Currency' in row:
                            amount = self._to_amount(
                                row['Amount in Pay Group Currency'],
                                account,
                                row['Pay Group Currency'],
                            )
                        else:
                            continue
                        if amount is None: continue
                        txn.postings.append(
                            Posting(
                                account=account,
                                units=amount,
                                cost=None,
                                meta={'workday_payroll_posting_description': f'{section_name}: {row.iloc[0]}'},
                                price=None,
                                flag=None))

            if len(txn.postings) > 0:
                imported_transactions_by_file.setdefault(relative_filename, []).append(txn)
                if relative_filename not in existing_transactions_by_file:
                    results.add_pending_entry(ImportResult(date=txn.date, entries=[txn], info=None))

        # Report transactions in the journal that have metadata that should
        # associate them with a source file, but that source file is not found.
        for filename, transactions in existing_transactions_by_file.items():
            num_expected = len(imported_transactions_by_file.get(filename, []))
            if len(transactions) == num_expected: continue
            num_extra = len(transactions) - num_expected
            results.add_invalid_reference(
                InvalidSourceReference(num_extra,
                                       [(transaction, None) for transaction in transactions]))


    def is_posting_cleared(self, posting: Posting):
        return (posting.meta is not None) and ('workday_payroll_posting_description' in posting.meta)


def load(spec, log_status):
    return WorkdayPayrollSource(log_status=log_status, **spec)
