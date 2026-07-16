# Examples

Here are some example queries you can try with the Northwind sample database.

## Basic Queries

### List all customers from Germany

> *"Show me all customers from Germany"*

**Generated SQL:**

```sql
SELECT * FROM Customers WHERE Country = 'Germany'
```

### Top 5 most expensive products

> *"What are the top 5 most expensive products?"*

**Generated SQL:**

```sql
SELECT ProductName, UnitPrice
FROM Products
ORDER BY UnitPrice DESC
LIMIT 5
```

### Count of orders by year

> *"How many orders were placed in each year?"*

**Generated SQL:**

```sql
SELECT strftime('%Y', OrderDate) AS Year,
       COUNT(*) AS OrderCount
FROM Orders
GROUP BY Year
ORDER BY Year
```

## Geography Queries

### Suppliers in the USA

> *"Who are our suppliers in the USA?"*

**Generated SQL:**

```sql
SELECT CompanyName, ContactName, City, Phone
FROM Suppliers
WHERE Country = 'USA'
```

### Customers in London

> *"List customers from London"*

**Generated SQL:**

```sql
SELECT CompanyName, ContactName, Phone
FROM Customers
WHERE City = 'London'
```

## Aggregation Queries

### Total sales by category

> *"Show total sales by category"*

**Generated SQL:**

```sql
SELECT Categories.CategoryName,
       ROUND(SUM("Order Details".Quantity * "Order Details".UnitPrice), 2) AS TotalSales
FROM Categories
JOIN Products ON Categories.CategoryID = Products.CategoryID
JOIN "Order Details" ON Products.ProductID = "Order Details".ProductID
GROUP BY Categories.CategoryName
ORDER BY TotalSales DESC
```

### Products that need reordering

> *"Which products are low in stock?"*

**Generated SQL:**

```sql
SELECT ProductName, UnitsInStock, ReorderLevel
FROM Products
WHERE UnitsInStock < ReorderLevel
ORDER BY UnitsInStock ASC
```

## Follow-up Queries

AskYourDB supports conversational follow-ups:

**User:** *"Show me all customers from Germany"*

**User:** *"What about France?"* 🔁 *(automatically rewritten to: "Show me all customers from France")*

**User:** *"And those starting with C?"* 🔁 *(automatically rewritten based on context)*

## Database Management

1. Click **Manage DB** in the header
2. Upload your own `.db`, `.sqlite`, or `.sqlite3` files
3. Switch between databases seamlessly
4. The app automatically re-analyzes the schema

---

> Try these queries with the **Chinook** database too — it has artists, albums, tracks, invoices, and customers!
