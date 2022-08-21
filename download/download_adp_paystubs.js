// 1. Log into ADP.
// 2. Go to https://my.adp.com/v1_0/O/A/payStatements?adjustments=yes&numberoflastpaydates=300.
// 3. Run the following code in the JS console:

var lastFetchedDate = "2022-07-29";

function sleep(ms) {
   return new Promise(resolve => setTimeout(resolve, ms));
}

var xhr = new XMLHttpRequest();
xhr.open('GET', 'https://my.adp.com/v1_0/O/A/payStatements?adjustments=yes&numberoflastpaydates=300');
xhr.setRequestHeader("Access-Control-Allow-Origin", "*");
xhr.onload = async function() {
    if (xhr.status === 200) {
        var rawData = JSON.parse(xhr.responseText);
        for (var index = rawData.payStatements.length - 1; index >= 0; --index) {
            var entry = rawData.payStatements[index];
            if (entry.payDate <= lastFetchedDate) continue;
            {
                var a = document.createElement('a');
                a.download = entry.payDate + ".json";
                a.href = "https://my.adp.com" + entry.payDetailUri.href;
                document.body.appendChild(a);
                await sleep(500);
                a.click();
                delete a;
            }
            {
                var a = document.createElement('a');
                a.download = entry.payDate + ".pdf";
                a.href = "https://my.adp.com" + entry.statementImageUri.href.substring(3);
                document.body.appendChild(a);
                await sleep(500);
                a.click();
                delete a;
            }
        }
    } else {
        console.log('Request failed.  Returned status of ' + xhr.status);
    }
};
xhr.send();
