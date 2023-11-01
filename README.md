# beancount-import-sources

A collection of sources for [beancount-import](https://github.com/jbms/beancount-import).

To install:

```sh
pip3 install git+https://github.com/ankurdave/beancount_import_sources.git
```

Example usage:

```sh
python3 ./run_beancount_import_example.py
```

## Data sources

- [`beancount_import_sources.adp_payroll_source`](beancount_import_sources/adp_payroll_source.py): Imports ADP paystubs in JSON format. ADP exposes this data through a REST API. Follow the instructions in [`download/download_adp_paystubs.js`](download/download_adp_paystubs.js).

- [`beancount_import_sources.boa_mortgage_csv_source`](beancount_import_sources/boa_mortgage_csv_source.py): Imports Bank of America mortgage statements in CSV format.

- [`beancount_import_sources.cashapp_csv_source`](beancount_import_sources/cashapp_csv_source.py): Imports Cash App transactions in CSV format. Cash App offers CSV statements for manual download. Follow the instructions in [`beancount_import_sources/cashapp_csv_source.py`](beancount_import_sources/cashapp_csv_source.py).

- [`beancount_import_sources.costco_receipt_source`](beancount_import_sources/costco_receipt_source.py): Imports Costco receipts in JSON format. Costco exposes this data through a GraphQL API. Follow the instructions in [`download/download_costco_receipts.js`](download/download_costco_receipts.js).

- [`beancount_import_sources.emburse_chrome_river_source`](beancount_import_sources/emburse_chrome_river_source.py): Imports Emburse Chrome River reimbursements in CSV format. Follow the instructions in [`beancount_import_sources.emburse_chrome_river_source`](beancount_import_sources/emburse_chrome_river_source.py).

- [`beancount_import_sources.venmo_json_source`](beancount_import_sources/venmo_json_source.py): Imports Venmo transactions in JSON format. Venmo exposes this data through a [REST API](https://github.com/mmohades/VenmoApiDocumentation). Follow the instructions in [`beancount_import_sources/venmo_json_source.py`](beancount_import_sources/venmo_json_source.py).

- [`beancount_import_sources.workday_payroll_source`](beancount_import_sources/workday_payroll_source.py): Imports Workday payslips in XLSX format. Follow the instructions in [`beancount_import_sources.workday_payroll_source`](beancount_import_sources/workday_payroll_source.py).
