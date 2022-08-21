# beancount-import-sources

A collection of sources for [beancount-import](https://github.com/jbms/beancount-import).

To install:

```sh
pip3 install git+https://github.com/ankurdave/beancount-import-sources.git
```

Example usage:

```sh
python3 ./run_beancount_import_example.py
```

## Data sources

- [`beancount_import_sources.sources.adp_payroll_source`](sources/adp_payroll_source.py): Imports ADP paystubs in JSON format. ADP exposes this data through a REST API. Follow the instructions in [`download/download_adp_paystubs.js`](download/download_adp_paystubs.js).

- [`beancount_import_sources.sources.cashapp_csv_source`](sources/cashapp_csv_source.py): Imports Cash App transactions in CSV format. Cash App offers CSV statements for manual download. Follow the instructions in [`sources/cashapp_csv_source.py`](sources/cashapp_csv_source.py).

- [`beancount_import_sources.sources.costco_receipt_source`](sources/costco_receipt_source.py): Imports Costco receipts in JSON format. Costco exposes this data through a GraphQL API. Follow the instructions in [`download/download_costco_receipts.js`](download/download_costco_receipts.js).

- [`beancount_import_sources.sources.venmo_json_source`](sources/venmo_json_source.py): Imports Venmo transactions in JSON format. Venmo exposes this data through a [REST API](https://github.com/mmohades/VenmoApiDocumentation). Follow the instructions in [`sources/venmo_json_source.py`](sources/venmo_json_source.py).
