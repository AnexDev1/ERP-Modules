{
    "name": "Inventory Product Category",
    "version": "19.0.1.0.0",
    "category": "Inventory",
    "summary": "Detailed category policies for Pharma",
    "author": "",
    "depends": ["product", "stock", "sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/product_category_views.xml",
    ],
    "installable": True,
    "application": False,
}
