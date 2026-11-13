# SST Guide for Accounts Payable (simplified demo rules)

These are simplified internal rules for this demo company, not tax advice.

- Only an SST-registered supplier may charge SST on its bill.
- Service tax for taxable services is booked with tax code **SV8** (8%).
- Sales tax on taxable goods is booked with **ST10** (10%) or **ST5** (5%) as printed on the bill.
- A supplier that is **not SST-registered** must be booked with tax code **NT** and tax amount 0.
  Any SST charged by a non-registered supplier is an error: hold the bill and ask the supplier
  for a corrected invoice.
- Check: `tax_amount` must equal `amount_excl_tax x rate` of the tax code (rounded to 2 decimals).
