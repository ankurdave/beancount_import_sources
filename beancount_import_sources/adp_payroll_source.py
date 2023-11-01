"""Source for ADP paystubs in JSON format.

ADP exposes this data through a REST API. Follow the instructions in
`../download/download_adp_paystubs.js` to download it.

Example usage:

    data_dir = os.path.dirname(__file__)
    data_sources = [
        dict(
            module='beancount_import_sources.adp_payroll_source',
            company_name='Hooli',
            earning_account_map={
                'Earning: Regular': 'Income:Hooli:Salary:Base',
                'Earning: Retro': 'Income:Hooli:Salary:Base',
                'Earning: Bonus': 'Income:Hooli:Salary:Bonus',
                'Earning: Spot': 'Income:Hooli:Salary:Bonus',
            },
            deduction_code_and_date_to_account= lambda deduction_code_name, date: {
                'Taxes: Federal Income Tax': f'Expenses:Tax:FY{date.year}:Income:Federal',
                'Taxes: Social Security Tax': f'Expenses:Tax:FY{date.year}:Income:SocialSecurity',
                'Taxes: Medicare Tax': f'Expenses:Tax:FY{date.year}:Income:Medicare',
                'Taxes: Medicare Surtax': f'Expenses:Tax:FY{date.year}:Income:Medicare',
                'Taxes: CA State Income Tax': f'Expenses:Tax:FY{date.year}:Income:California',
                'Taxes: CA SDI Tax': f'Expenses:Tax:FY{date.year}:Income:CaliforniaUnemploymentAndDisabilityInsurance',
                'Taxes: CA SUI/SDI Tax': f'Expenses:Tax:FY{date.year}:Income:CaliforniaUnemploymentAndDisabilityInsurance',
                'Benefits: Dental Pretax': 'Expenses:Healthcare:Insurance',
                'Benefits: Medical Pretax': 'Expenses:Healthcare:Insurance',
                'Benefits: Vision Pretax': 'Expenses:Healthcare:Insurance',
                'Benefits: Hsa Pretax': 'Assets:HooliHSA:Cash',
                'Retirement: 401K Plan': 'Assets:Hooli401k:Cash',
                'Other: After-Tax 415C': 'Assets:Hooli401k:Cash',
                'Other: Reimbursement': 'Assets:Receivable:Hooli',
                'Banking: Checking 1': 'Assets:BankOfAmerica:Checking',
            }[deduction_code_name],
            memo_map={
                'grouptermlife': [
                    'Income:Hooli:GroupTermLife',
                    'Expenses:LifeInsurance:HooliGroupTermLife',
                ],
                'erhsa': [
                    'Income:Hooli:HSAContribution',
                    'Assets:HooliHSA:Cash',
                ],
            },
            data_dir=data_dir,
            json_filenames=glob.glob(os.path.join(data_dir, 'data/Hooli/Salary/*.json')),
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
                 company_name,
                 earning_account_map, deduction_code_and_date_to_account,
                 memo_map, **kwargs):
        super().__init__(**kwargs)
        self.company_name = company_name
        self.earning_account_map = earning_account_map
        self.deduction_code_and_date_to_account = deduction_code_and_date_to_account
        self.memo_map = memo_map

class AdpPayrollSource(Config, Source):
    def __init__(self, data_dir: str, json_filenames: List[str],
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir = data_dir
        self.json_filenames = sorted([os.path.realpath(x) for x in json_filenames])
        self.example_posting_key_extractors = {'adp_payroll_posting_description': None}

    @property
    def name(self):
        return 'adp_payroll'

    def to_amount(self, json_amount) -> Amount:
        return Amount(currency=json_amount['currencyCode'], number=json_amount['amountValue'])

    def prepare(self, journal, results: SourceResults):
        for adp_account, beancount_account in self.earning_account_map.items():
            results.add_account(beancount_account)
        # Scan the journal to see which files we have already imported.
        existing_transactions_by_file = dict()
        for transaction in journal.all_entries:
            if not isinstance(transaction, Transaction): continue
            meta = transaction.meta
            if (meta and 'adp_payroll_source_file' in meta):
                filename = meta['adp_payroll_source_file']
                existing_transactions_by_file.setdefault(filename, []).append(transaction)

        # Read all files and add pending entries not already imported into the journal.
        imported_transactions_by_file = dict()
        for filename in self.json_filenames:
            self.log_status('adp_payroll: processing %s' % (filename, ))
            with open(filename) as f:
                data = json.load(f, parse_float=Decimal)
            date = datetime.datetime.strptime(data['payStatement']['payDate'], '%Y-%m-%d').date()
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
            txn.meta['adp_payroll_source_file'] = relative_filename

            for earning in data['payStatement']['earnings']:
                if 'earningAmount' not in earning: continue
                desc = 'Earning: ' + earning['earningCodeName'].strip()
                earning_account = self.earning_account_map[desc]
                txn.postings.append(
                    Posting(
                        account=earning_account,
                        # ADP reports earnings as a positive number. Flip the sign to match
                        # accounting conventions (Income is negative).
                        units=-self.to_amount(earning['earningAmount']),
                        cost=None,
                        meta={'adp_payroll_posting_description': desc},
                        price=None,
                        flag=None))

            for deduction in data['payStatement']['deductions']:
                if 'deductionAmount' not in deduction: continue
                # ADP reports all deductions as negative numbers. Flip the sign to match accounting
                # conventions (Expenses are positive).
                amount = -self.to_amount(deduction['deductionAmount'])
                deduction_code_name = deduction['deductionCategoryCodeName'] + ': ' + deduction['CodeName'].strip()
                deduction_account = self.deduction_code_and_date_to_account(deduction_code_name, date)
                txn.postings.append(
                    Posting(
                        account=deduction_account,
                        units=amount,
                        cost=None,
                        meta={'adp_payroll_posting_description': deduction_code_name},
                        price=None,
                        flag=None))

            for memo in data['payStatement']['memos']:
                if memo['nameCode']['codeValue'] not in self.memo_map: continue
                memo_income_account, memo_expense_account = \
                    self.memo_map[memo['nameCode']['codeValue']]
                if 'memoAmount' not in memo: continue
                amount = self.to_amount(memo['memoAmount'])
                memo_description = memo['nameCode']['shortName'].strip()
                txn.postings.append(
                    Posting(
                        account=memo_income_account,
                        units=-amount,
                        cost=None,
                        meta={'adp_payroll_posting_description': memo_description},
                        price=None,
                        flag=None))
                txn.postings.append(
                    Posting(
                        account=memo_expense_account,
                        units=amount,
                        cost=None,
                        meta={'adp_payroll_posting_description': memo_description},
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
        return (posting.meta is not None) and ('adp_payroll_posting_description' in posting.meta)

def load(spec, log_status):
    return AdpPayrollSource(log_status=log_status, **spec)
