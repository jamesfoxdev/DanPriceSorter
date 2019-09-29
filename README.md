# DanPriceSorter
Automatically scrape products from Dan Murphys, categorise them, sort them by price
per standard, and expose them through a RESTful API.

This is also the backend for [THE GROGNATOR](https://play.google.com/store/apps/details?id=jamesfoxdev.the_grogonator_v2&hl=en). Check it out.

## Usage
First we must run the shadow script to download Dan Murphy's catalouge
```
python3 danShadow.py
```
Then we can expose the generated database at `data/danDB.db` through an API
```
node danPriceSorter.js
```
The database will automatically update itself every day at 6am (if its running at that time). This is to provent accidentally causing a DOS on Dan Murphy's servers.

## Products
A Dan Murphy's product is comprised of these columns

|Field|Description|Type|
|--|--|--|
|Type|The type of alcohol it is (category)|`string`|
|Stockcode|The stockcode of the item|`string`|
|UrlFriendlyName|The name of the item as specified in the URL|`string`|
|AverageRating|The product's customer rating|`float`|
|ReviewCount|The amount of reviews customers have given the product|`int`|
|SinglePrice|The price of the lowest amount of alcohol you can buy in a pack (E.G a six pack). But wine and spirits a single is a bottle, not a pack (I know it's kind of dumb, git blame Dan Murphy)|`float`|
|CasePrice|The price of the highest amount of alcohol you can buy in one purchase (E.G a case of beer, or six bottles of wine)|`float`|
|SinglePriceAmount|The amount of items in a 'single'|`int`|
|CasePriceAmount|The amount of items in a 'case' (E.G 6 for wine or 24 for beer, etc)|`int`|
|SingleMessage|A text annotation for the single amount (per bottle, per six pack, etc)|`string`|
|CaseMessage|A text annotation for the double amount (per case, per 2 casks, etc)|`string`|
|Promo|Is the product currently part of a promotion|`bool`|
|Description|A description of the product|`string`|
|DirectFromSupplier|Does Dan Murphy's stock the product or does it come directly from the supplier|`bool`|


Endpoints that return products will return a JSON array comprised of a series of product objects (with the above specifications)

## API Endpoints
### `POST /category/:category`
Gives an array of products matching a certain category. These categories are:
- spirits
- white wine
- champagne-sparkling
- whisky
- red wine
- beer
- cider

The query payload should contain two fields

|Description|Field|Data Type|
|--|--|--|
|Allow external suppliers to populate results|`externSupplier`|`boolean`|
|The page number to return|`page`|`uint`|

### `POST /top`
Returns an array of products sorted by price per standard drink. The query payload should contain two fields:

|Description|Field|Data Type|
|--|--|--|
|Allow external suppliers to populate results|`externSupplier`|`boolean`|
|The page number to return|`page`|`uint`|

### `POST /search`
Return a list of products matching a search query. The query payload should contain three fields:

|Description|Field|Data Type|
|--|--|--|
|The search query|`query`|`string`|
|Allow external suppliers to populate results|`externSupplier`|`boolean`|
|The page number to return|`page`|`uint`|

### `GET /updated`
Returns a UNIX timestamp of when the listings were last updated

### `GET /`
Returns how many products are in the database and when it was last updated
