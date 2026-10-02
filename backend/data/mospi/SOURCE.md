# backend/data/mospi/

MoSPI (National Statistical Office) Consumer Price Index, from the CPI portal
(esankhyiki.mospi.gov.in). Base 2012 = 100. NOT scraped — official statistic.

## cpi_air_fare_item.csv
CPI **item-level** index: *"Air Fare (normal): Economy Class (adult)"*.
Monthly, 2014 → Dec 2025. Columns: baseyear, year, month_code, month, item,
index, inflation, status.

**This is the back-test target** — the problem statement requires 30+ days of
results validated against DGCA/MoSPI monthly average-fare data, and this CPI
item is exactly that: MoSPI's own airfare index, built from collected fares.
`scripts/backtest.py` aggregates the VAYU-SUCHAK APIx to monthly and compares
its month-over-month movement to this series.

## cpi_transport_subgroup.csv
CPI sub-group *"Transport and Communication"* (broader — includes fuel, rail/bus
fares, telecom). All-India + all states, Rural/Urban/Combined, monthly 2022–2025.
Used as the secondary CPI reference line on the dashboard.

## Refresh
Re-download from the CPI portal → CPI (Combined) → Select Level: Item →
"Air Fare (normal): Economy Class(adult)" → all years → Download. Add 2026
months when MoSPI publishes them (CPI lags ~6 weeks).
