# -*- coding: utf-8 -*-
"""Display names that correct or tidy the descriptions stored in the data.

The data describes each column once for all tables, so a column such as pop_tot reads
"Total Population" even in the table of average ages. Labels here are keyed by the table's
base name (without the gmnd/krs/rgn suffix) and take precedence over the stored description.
"""

# Column labels that are only right for one table
TABLE_LABELS = {
    "demography_avg_age": {"pop_tot": "Average age, total", "pop_mle": "Average age, male",
                           "pop_fml": "Average age, female"},
    "living_size_of_hshld": {"pop_tot": "Households, total"},
    "tourism_trvl_cmpn": {"estb": "Accommodation establishments", "arrv_tgthr": "Arrivals, total",
                          "arrv_frgnr": "Arrivals from abroad", "ngts_tgthr": "Overnight stays, total",
                          "ngts_frgnr": "Overnight stays from abroad", "stay_days": "Average length of stay (days)",
                          "beds_used": "Bed occupancy (%)"},
    "working_dev_emp_scl_ins_cntrb_cmtr": {"feature": "Employee group"},
}

# Column labels that apply to every table
COLUMN_LABELS = {
    "year": "Year",
    "pop_u20": "Population under 20",
    "pop_a65": "Population 65 and over",
    "pop_a20_u65": "Population 20 to under 65",
    "age_u20": "Under 20",
    "age_20_40": "20 to under 40",
    "age_40_60": "40 to under 60",
    "age_60_85": "60 to under 85",
    "age_85_a": "85 and over",
    "mvaway_tgthr": "Moved out, total",
    "mvaway_male": "Moved out, male",
    "nwcmrs_tgthr": "Moved in, total",
    "nwcmrs_male": "Moved in, male",
    "netmgr_tgthr": "Net migration, total",
    "netmgr_male": "Net migration, male",
    "blnc_tgthr": "Births minus deaths, total",
    "blnc_male": "Births minus deaths, male",
    "pop_den_pekm": "Population density (per km²)",
    "area_ha": "Area (ha)",
}

TITLE_LABELS = {
    "tourism_trvl_cmpn": "Accommodation and Overnight Stays",
}


def tidy(description: str) -> str:
    # "Employees in Manufacturing %age" reads better as "Employees in Manufacturing (%)"
    return description.replace(" %age", " (%)")
