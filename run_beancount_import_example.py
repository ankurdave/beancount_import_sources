#!/usr/bin/env python3

import glob
import os
import json
import sys


def run_reconcile(extra_args):
    import beancount_import.webserver

    journal_dir = os.path.dirname(__file__)
    data_dir = os.path.dirname(__file__)

    data_sources = [
        dict(
            module='beancount_import_sources.sources.adp_payroll_source',
            company_name='Hooli',
            earning_account_map={
                'Earning: Regular': 'Income:Hooli:Salary:Base',
                'Earning: Retro': 'Income:Hooli:Salary:Base',
                'Earning: Bonus': 'Income:Hooli:Salary:Bonus',
                'Earning: Spot': 'Income:Hooli:Salary:Bonus',
            },
            deduction_code_and_date_to_account= lambda deduction_code_name, date: {
                'Taxes: Federal Income Tax': f'Expenses:Tax:FY{date.year}:Income:Federal',
                'Taxes: Social Security Tax': f'Expenses:Tax:FY{date.year}:SocialSecurity',
                'Taxes: Medicare Tax': f'Expenses:Tax:FY{date.year}:Medicare',
                'Taxes: Medicare Surtax': f'Expenses:Tax:FY{date.year}:Medicare',
                'Taxes: CA State Income Tax': f'Expenses:Tax:FY{date.year}:Income:California',
                'Taxes: CA SDI Tax': f'Expenses:Tax:FY{date.year}:CaliforniaUnemploymentAndDisabilityInsurance',
                'Taxes: CA SUI/SDI Tax': f'Expenses:Tax:FY{date.year}:CaliforniaUnemploymentAndDisabilityInsurance',
                'Taxes: PA State Income Tax': f'Expenses:Tax:FY{date.year}:Income:Pennsylvania',
                'Taxes: PA SUI Tax': f'Expenses:Tax:FY{date.year}:PennsylvaniaUnemploymentInsurance',
                'Taxes: Pittsburgh C Income Tax': f'Expenses:Tax:FY{date.year}:Income:Pittsburgh',
                'Taxes: Pittsburgh C Local Svc Tax': f'Expenses:Tax:FY{date.year}:PittsburghLocalServicesTax',
                'Benefits: Dental Pretax': 'Expenses:Healthcare:Insurance',
                'Benefits: Medical Pretax': 'Expenses:Healthcare:Insurance',
                'Benefits: Vision Pretax': 'Expenses:Healthcare:Insurance',
                'Retirement: 401K Plan': 'Assets:Fidelity:Hooli401k:Cash',
                'Other: After-Tax 415C': 'Assets:Fidelity:Hooli401k:Cash',
                'Other: Reimbursement': 'Assets:Receivable:Hooli',
                'Banking: Checking 1': 'Assets:BankOfAmerica:Checking',
            }[deduction_code_name],
            group_term_life_income_account='Income:Hooli:GroupTermLife',
            group_term_life_expenses_account='Expenses:LifeInsurance:HooliGroupTermLife',
            data_dir=data_dir,
            json_filenames=glob.glob(os.path.join(data_dir, 'data/Hooli/Salary/*.json'))),
        dict(
            module='beancount_import_sources.sources.venmo_json_source',
            data_dir=data_dir,
            self_username='John-Doe',
            venmo_assets_account='Assets:Venmo',
            json_filenames=glob.glob(os.path.join(data_dir, 'data/Venmo/*.json'))),
        dict(
            module='beancount_import_sources.sources.cashapp_csv_source',
            cashapp_account='Assets:CashApp',
            data_dir=data_dir,
            csv_filenames=glob.glob(os.path.join(data_dir, 'data/CashApp/*.csv'))),
        dict(
            module='beancount_import_sources.sources.costco_receipt_source',
            food_stamp_eligible_expenses_account='Expenses:Food:Groceries:Costco',
            health_fsa_eligible_expenses_account='Expenses:Healthcare:Medicine:Costco',
            other_expenses_account='Expenses:Housing:Goods:Costco',
            discount_expenses_account='Expenses:Costco:Discounts',
            sales_tax_expenses_account='Expenses:Tax:Sales:Costco',
            rewards_tender_account='Income:Rewards:Costco',
            cash_tender_account='Expenses:Cash',
            tender_account_from_description=lambda tender_description: {
                'COSTCO VISA, 1234': 'Liabilities:Citi:Costco',
            }[tender_description],
            data_dir=data_dir,
            json_filenames=glob.glob(os.path.join(data_dir, 'data/Costco/*.json'))),
    ]

    output_file = 'main.beancount'

    beancount_import.webserver.main(
        extra_args,
        journal_input=os.path.join(journal_dir, 'main.beancount'),
        ignored_journal=os.path.join(journal_dir, 'ignored.beancount'),
        default_output=os.path.join(journal_dir, output_file),
        open_account_output_map=[
            ('.*', os.path.join(journal_dir, output_file)),
        ],
        balance_account_output_map=[
            ('.*', os.path.join(journal_dir, output_file)),
        ],
        price_output=os.path.join(journal_dir, output_file),
        data_sources=data_sources,
    )


if __name__ == '__main__':
    run_reconcile(sys.argv[1:])
