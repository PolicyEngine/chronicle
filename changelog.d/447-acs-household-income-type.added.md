Add four Census ACS 2024 1-year packages of household income and household
type (chronicle#447 item 3), from the Census Bureau's API responses, with margins of error:
B19001 household income in 16 brackets for the United States
(`census-acs1-b19001-national-2024`), for each state, DC and Puerto Rico
(`census-acs1-b19001-state-2024`) and for each congressional district of the
119th Congress, DC's delegate district and Puerto Rico's resident commissioner
district (`census-acs1-b19001-district-2024`); and B11001 household type for
those 437 districts (`census-acs1-b11001-district-2024`). The B19001 brackets
take the ACS 5-year county package's `income_range` values and household
income bounds. In the published files the district rows add up exactly to
their state row, the states and DC to the United States row, and B19001's
total equals B11001's in every geography. The label register lists the
districts and the brackets that two or more packages now emit.
