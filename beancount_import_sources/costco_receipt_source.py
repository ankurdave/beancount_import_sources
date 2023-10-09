"""Source for Costco receipts in JSON format.

The resulting transactions can have a large number of postings, since there is at least one per item
purchased. To avoid triggering exponential behavior in beancount-import, the Expenses account for
each item must be specified explicitly in the configuration. We use the item identifier and tax flag
to categorize each item into one of 3 categories: (1) food-stamp eligible, (2) health FSA eligible,
and (3) all other purchases. This source is authoritative for each of these 3 accounts.

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
                 food_stamp_eligible_expenses_account,
                 health_fsa_eligible_expenses_account,
                 other_expenses_account,
                 discount_expenses_account,
                 sales_tax_expenses_account,
                 rewards_tender_account,
                 cash_tender_account,
                 tender_account_from_description,
                 **kwargs):
        super().__init__(**kwargs)
        self.food_stamp_eligible_expenses_account = food_stamp_eligible_expenses_account
        self.health_fsa_eligible_expenses_account = health_fsa_eligible_expenses_account
        self.other_expenses_account = other_expenses_account
        self.discount_expenses_account = discount_expenses_account
        self.sales_tax_expenses_account = sales_tax_expenses_account
        self.rewards_tender_account = rewards_tender_account
        self.cash_tender_account = cash_tender_account
        self.tender_account_from_description = tender_account_from_description


class CostcoReceiptSource(Config, Source):
    def __init__(self, data_dir: str, json_filenames: List[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir = data_dir
        self.json_filenames = sorted([os.path.realpath(x) for x in json_filenames])
        self.example_posting_key_extractors = {
            'costco_receipt_item_description': None,
            'costco_receipt_item_identifier': None,
            'costco_receipt_tax_flag': None,
            'costco_receipt_tender_description': None,
        }

    @property
    def name(self):
        return 'costco_receipt'

    def prepare(self, journal, results: SourceResults):
        results.add_account(self.food_stamp_eligible_expenses_account)
        results.add_account(self.health_fsa_eligible_expenses_account)
        results.add_account(self.other_expenses_account)
        results.add_account(self.discount_expenses_account)
        results.add_account(self.sales_tax_expenses_account)
        results.add_account(self.rewards_tender_account)

        # Scan the journal to see which transactions we have already imported.
        existing_transactions_by_barcode = dict()
        for transaction in journal.all_entries:
            if not isinstance(transaction, Transaction): continue
            meta = transaction.meta
            if (meta and 'costco_receipt_barcode' in meta):
                existing_transactions_by_barcode[meta['costco_receipt_barcode']] = transaction

        # Read all files and add pending entries not already imported into the journal.
        imported_transactions_by_barcode = dict()
        for filename in self.json_filenames:
            self.log_status('costco_receipt: processing %s' % (filename, ))
            relative_filename = os.path.relpath(filename, start=self.data_dir)
            with open(filename) as f:
                data = json.load(f, parse_float=Decimal)
            for order in data:
                if order['documentType'] != 'WarehouseReceiptDetail': continue
                date = datetime.datetime.strptime(order['transactionDateTime'], '%Y-%m-%dT%H:%M:%S').date()
                txn = Transaction(
                    meta=collections.OrderedDict(),
                    date=date,
                    flag='*',
                    payee='Costco',
                    narration=f"Costco warehouse #{order['warehouseNumber']} {order['warehouseShortName']} - {order['transactionType']} - {order['totalItemCount']} items",
                    tags=EMPTY_SET,
                    links=EMPTY_SET,
                    postings=[])
                txn.meta['costco_receipt_source_file'] = relative_filename
                txn.meta['costco_receipt_order_datetime'] = order['transactionDateTime']
                txn.meta['costco_receipt_order_type'] = order['transactionType']
                txn.meta['costco_receipt_barcode'] = order['transactionBarcode']
                warehouse_address_keys = [
                    'warehouseName', 'warehouseAddress1', 'warehouseAddress2', 'warehouseCity',
                    'warehouseState', 'warehouseCountry', 'warehousePostalCode'
                ]
                warehouse_address_parts = [str(order[k]) for k in warehouse_address_keys if order[k]]
                txn.meta['costco_receipt_warehouse'] = ', '.join(warehouse_address_parts)

                # Gather all rebates so we can look them up for each item.
                rebate_by_item_number = {}
                for item in order['itemArray']:
                    item_number = self._rebated_item_number_if_rebate(item)
                    if item_number is not None:
                        rebate_by_item_number[item_number] = item['amount']

                if len(rebate_by_item_number) == 0:
                    # Older receipts group all rebates under an "instant savings" category. Since we
                    # can't associate them with individual items, add these rebates as a separate
                    # posting.
                    savings = order['instantSavings']
                    if savings:
                        txn.postings.append(
                            Posting(
                                account=self.discount_expenses_account,
                                units=Amount(currency='USD', number=Decimal(-savings)),
                                cost=None,
                                meta={},
                                price=None,
                                flag=None))

                for item in order['itemArray']:
                    if self._rebated_item_number_if_rebate(item) is not None: continue
                    item_description_keys = [
                        'itemNumber', 'itemDescription01', 'itemDescription02'
                    ]
                    item_description_parts = [str(item[k]) for k in item_description_keys if item[k]]
                    item_amount = item['amount']
                    if str(item['itemNumber']) in rebate_by_item_number:
                        item_amount += rebate_by_item_number[str(item['itemNumber'])]
                    desc_list = re.sub(' +', ' ', ' '.join(item_description_parts)).strip()

                    if item['itemIdentifier'] == 'E':
                        item_account = self.food_stamp_eligible_expenses_account
                    elif item['itemIdentifier'] == 'F':
                        item_account = self.health_fsa_eligible_expenses_account
                    else:
                        item_account = self.other_expenses_account

                    txn.postings.append(
                        Posting(
                            account=item_account,
                            units=Amount(currency='USD', number=Decimal(item_amount)),
                            cost=None,
                            meta={
                                'costco_receipt_item_description': desc_list,
                                # 'E' for food stamp eligible, 'F' for FSA eligible, '' for neither.
                                'costco_receipt_item_identifier': item['itemIdentifier'],
                                # 'A' for taxable, '' for non-taxable.
                                'costco_receipt_tax_flag': item['taxFlag'],
                            },
                            price=None,
                            flag=None))

                txn.postings.append(
                    Posting(
                        account=self.sales_tax_expenses_account,
                        units=Amount(currency='USD', number=Decimal(order['taxes'])),
                        cost=None,
                        meta={},
                        price=None,
                        flag=None))

                for tender in order['tenderArray']:
                    tender_description_keys = [
                        'tenderDescription', 'displayAccountNumber'
                    ]
                    tender_description_parts = [str(tender[k]) for k in tender_description_keys if tender[k]]
                    tender_description = ', '.join(tender_description_parts)

                    # Determine which account paid for this order. We don't want to use
                    # Expenses:FIXME for this posting, because that would produce a transaction that
                    # might appear to reconcile with numerous other transactions.
                    if 'Rebate' in tender_description:
                        tender_account = self.rewards_tender_account
                    elif tender_description == 'Cash':
                        tender_account = self.cash_tender_account
                    else:
                        tender_account = self.tender_account_from_description(tender_description)

                    txn.postings.append(
                        Posting(
                            account=tender_account,
                            units=Amount(currency='USD', number=Decimal(-tender['amountTender'])),
                            cost=None,
                            meta={
                                'costco_receipt_tender_description': tender_description,
                            },
                            price=None,
                            flag=None))

                imported_transactions_by_barcode[order['transactionBarcode']] = txn
                if order['transactionBarcode'] not in existing_transactions_by_barcode:
                    results.add_pending_entry(ImportResult(date=txn.date, entries=[txn], info=None))

        # Report transactions in the journal have metadata that should associate
        # them with a source receipt, but that source receipt is not found.
        for barcode, txn in existing_transactions_by_barcode.items():
            if barcode not in imported_transactions_by_barcode:
                results.add_invalid_reference(InvalidSourceReference(1, (txn, None)))

    def is_posting_cleared(self, posting: Posting):
        return True

    def _rebated_item_number_if_rebate(self, item) -> int:
        if (item['itemDescription01'] or '').startswith('/'):
            description = item['itemDescription01']
        elif (item['frenchItemDescription1'] or '').startswith('/'):
            # Receipts after ~2022-12-04 have used the frenchItemDescription1
            # key to store the rebated item number.
            description = item['frenchItemDescription1']
        else:
            return None

        # Descriptions like "/1575321" indicate a rebate on that item number.
        return description.lstrip('/')


def load(spec, log_status):
    return CostcoReceiptSource(log_status=log_status, **spec)
