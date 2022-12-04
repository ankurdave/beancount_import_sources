// 1. Go to https://www.costco.com/OrderStatusCmd.
// 2. Run the following code in the JS console:

function getToken() {
    return new Promise(function (resolve, reject) {
        var tokenXhr = new XMLHttpRequest();
        tokenXhr.open('GET', 'https://www.costco.com/user-session-token');
        tokenXhr.setRequestHeader("Access-Control-Allow-Origin", "*");
        tokenXhr.onload = async function() {
            if (tokenXhr.status === 200) {
                resolve(tokenXhr.response);
            } else {
                reject(tokenXhr.status);
            }
        };
        tokenXhr.send();
    });
}

async function listReceipts(startDate, endDate) {
    var token = await getToken();
    return await new Promise(function (resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.responseType = 'json';
        xhr.open('POST', 'https://api.costco.com/ebusiness/order/v1/orders/graphql');
        xhr.setRequestHeader("Access-Control-Allow-Origin", "*");
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('costco.env', 'PROD');
        xhr.setRequestHeader('costco.service', 'restOrders');
        xhr.setRequestHeader('client-identifier', '481b1aec-aa3b-454b-b81b-48187e28f205');
        xhr.setRequestHeader('costco-x-authorization', 'Bearer ' + token);
        const listReceiptsQuery = {
            "query": `
                query {
                    receipts(startDate: "${startDate}" endDate: "${endDate}") {
                        warehouseName
                        documentType
                        transactionDateTime
                        transactionDate
                        companyNumber
                        warehouseNumber
                        operatorNumber
                        warehouseName
                        warehouseShortName
                        registerNumber
                        transactionNumber
                        transactionType
                        transactionBarcode
                        total
                        warehouseAddress1
                        warehouseAddress2
                        warehouseCity
                        warehouseState
                        warehouseCountry
                        warehousePostalCode
                        totalItemCount
                        subTotal
                        taxes
                        total
                        itemArray {
                            itemNumber
                            itemDescription01
                            frenchItemDescription1
                            itemDescription02
                            frenchItemDescription2
                            itemIdentifier
                            unit
                            amount
                            taxFlag
                            merchantID
                            entryMethod
                        }
                        tenderArray {
                            tenderTypeCode
                            tenderDescription
                            amountTender
                            displayAccountNumber
                            sequenceNumber
                            approvalNumber
                            responseCode
                            transactionID
                            merchantID
                            entryMethod
                        }
                        couponArray {
                            upcnumberCoupon
                            voidflagCoupon
                            refundflagCoupon
                            taxflagCoupon
                            amountCoupon
                        }
                        subTaxes {
                            tax1
                            tax2
                            tax3
                            tax4
                            aTaxPercent
                            aTaxLegend
                            aTaxAmount
                            bTaxPercent
                            bTaxLegend
                            bTaxAmount
                            cTaxPercent
                            cTaxLegend
                            cTaxAmount
                            dTaxAmount
                        }
                        instantSavings
                        membershipNumber
                    }
                }`.replace(/\s+/g,' ')
        };
        xhr.onload = async function() {
            if (xhr.status === 200) {
                resolve(xhr.response.data.receipts);
            } else {
                reject(xhr.status);
            }
        };
        xhr.send(JSON.stringify(listReceiptsQuery));
    });
}

async function downloadReceipts() {
    var startDateStr = '01/01/2020';
    var endDate = new Date();
    var endDateStr = endDate.toLocaleDateString('en-US', {
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
    });
    var receipts = await listReceipts(startDateStr, endDateStr);
    console.log(`Got ${receipts.length} receipts, saving.`)
    {
        var a = document.createElement('a');
        a.download = `costco-${endDate.toISOString()}.json`
        a.href = window.URL.createObjectURL(new Blob([JSON.stringify(receipts, null, 2)], {type: 'text/plain'}));
        a.target = '_blank';
        document.body.appendChild(a);
        a.click();
    }
}

await downloadReceipts();
