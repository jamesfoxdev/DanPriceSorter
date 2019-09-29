const express = require('express')
const app = express()
const sqlite3 = require('sqlite3').verbose();
const schedule = require('node-schedule');
const spawn = require("child_process").spawn;

const PORT = 3000
const DATBASE_PATH = "data/danDB.db"
const CATEGORIES = ["spirits", "white wine", "champagne-sparkling", "whisky", "red wine", "beer", "cider"]
const PAGE_SIZE = 15

// Type, DirectFromSupplier, Offset
var SQL_CATEGORY_QUERY = `SELECT * from DanDB WHERE Type = ? and DirectFromSupplier <= ? ORDER BY IFNULL(SinglePricePerStandard, CasePricePerStandard) LIMIT ${PAGE_SIZE} OFFSET ?`
// DirectFromSupplier, Offset
var SQL_TOP_QUERY = `SELECT * from DanDB WHERE DirectFromSupplier <= ? ORDER BY IFNULL(SinglePricePerStandard, CasePricePerStandard) LIMIT ${PAGE_SIZE} OFFSET ?`
// Query
var SQL_SEARCH_QUERY = `SELECT * from DanDB WHERE producttitle LIKE ? and DirectFromSupplier <= ? ORDER BY IFNULL(SinglePricePerStandard, CasePricePerStandard) LIMIT ${PAGE_SIZE} OFFSET ?`
// Get the amount of products in the table
const SQL_PRODUCT_AMOUNT = "SELECT Count(*) FROM DanDB"

var lastUpdated = Math.floor(new Date() / 1000)

let db = new sqlite3.Database(DATBASE_PATH, (err) => {
    if (err) {
      return console.error(err.message);
    }
    console.log('Connected to ' + DATBASE_PATH);
});

function convertData(sqliteData){
    let arr = []
    sqliteData.forEach((row)=>{
        arr.push(row)
    })
    return arr
}

app.get('/', (req, res) => {
    db.get(SQL_PRODUCT_AMOUNT, (err,row) => {
        if(err){
            res.send({"pass":false, "reason":err})
        } else {
            res.send({
                "pass":true,
                "productCount":row['Count(*)'],
                "lastUpdated":lastUpdated
            })
        }
    })
})

// Return 50 listings sorted by price per standard in a category
app.get("/category/:category", (req, res) => {
    if(CATEGORIES.includes(decodeURIComponent(req.params.category))){
        rowOffset = parseInt(decodeURIComponent(req.query.page)) * PAGE_SIZE
        // Default to no external suppliers
        allowedExternSupplier = parseInt(decodeURIComponent(req.query.externSupplier))
        if(isNaN(allowedExternSupplier)){
            allowedExternSupplier = 0
        } else if(!(allowedExternSupplier == 1 || allowedExternSupplier == 0)){
            allowedExternSupplier = 0
        }

        if(isNaN(rowOffset)){
            rowOffset = 0
        }
        db.all(SQL_CATEGORY_QUERY,  req.params.category, allowedExternSupplier, rowOffset, function(err, rows){
            if(err){
                res.send({"pass":false, "error":err})
            } else {
                data = convertData(rows)
                res.send({
                    "data" : data,
                    "pass":true
                })
            }
        })
    } else {
        res.send({"pass":false, "error":"Unrecognisable catagory"})
    }
})

// Retreive the top listings sorted by price per standard, regardless of category
app.get("/top", (req, res) => {
    let pageNum = decodeURIComponent(req.query.page)
    rowOffset = parseInt(pageNum) * PAGE_SIZE
    // Default to no external suppliers
    allowedExternSupplier = parseInt(decodeURIComponent(req.query.externSupplier))

    if(isNaN(allowedExternSupplier)){
        allowedExternSupplier = 0
    } else if(allowedExternSupplier != 1 && allowedExternSupplier != 0){
        allowedExternSupplier = 0
    }

    if(isNaN(rowOffset)){
        rowOffset = 0
    }
    db.all(SQL_TOP_QUERY, allowedExternSupplier, rowOffset, function(err, rows){
        if(err){
            res.send({"pass":false, "error":err})
        } else {
            data = convertData(rows)
            res.send({
                "data" : data,
                "pass":true
            })
        }
    })
})

app.get("/search", (req, res)=>{
    var searchQuery = req.query.query
    let pageNum = decodeURIComponent(req.query.page)
    rowOffset = parseInt(pageNum) * PAGE_SIZE
    // Default to no external suppliers
    allowedExternSupplier = parseInt(decodeURIComponent(req.query.externSupplier))

    if(isNaN(allowedExternSupplier)){
        allowedExternSupplier = 0
    } else if(allowedExternSupplier != 1 && allowedExternSupplier != 0){
        allowedExternSupplier = 0
    }

    if(isNaN(rowOffset)){
        rowOffset = 0
    }
    if(searchQuery != "" && searchQuery){
        db.all(SQL_SEARCH_QUERY, `%${searchQuery}%`, allowedExternSupplier, rowOffset, function(err, rows){
            if(err){
                res.send({"pass":false, "error":err})
            } else {
                data = convertData(rows)
                res.send({
                    "data" : data,
                    "pass":true
                })
            }
        })
    } else {
        res.send({"pass":false, "reason":"No search query"})
    }
})

app.get("/updated", (req,res)=>{
    res.send(lastUpdated)
})

const server = app.listen(PORT, () => {
    var lastUpdated = 0
    console.log(`Dan Price Sorter API Listening On ${PORT}!`)
    // Start the auto-updater
    const updateDatabase = schedule.scheduleJob("6 * * *",function(){
        const databaseUpdater = spawn("python3",["bin/danShadow.py"])
        console.log("Updating database...")
        databaseUpdater.stderr.on("data", ()=>{
            console.error("Database updater has failed!")
        })
        lastUpdated = Math.floor(new Date() / 1000)
    })
})

process.on("SIGTERM", () => {
    console.log("Exiting...")
    server.close(()=>{
        db.close()
        process.exit(0)
    })
})