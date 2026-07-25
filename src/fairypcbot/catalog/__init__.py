"""Component resolution via external catalog (spec section 7).

LCSC part number is the universal primary key (`lcsc:CXXXXX`); EasyEDA is the data source used in
M2. Secondary sources (Digikey, Mouser, direct MPN) come later as additional resolvers,
implementing the same contract (`CatalogResolver`).
"""
