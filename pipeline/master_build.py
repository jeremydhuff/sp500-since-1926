"""Builds data/companies.json — the single master list of display companies.

Each entry carries:
  id, name, short, sector (French 12-industry code), color,
  yahoo   : ticker for the free tier (optional)
  match   : regex tested against every historical CRSP company name of a PERMCO
            (first matching entry wins, so order matters — specific before general)

Colours: a handful of brand-anchored hues (silver Apple, green Nvidia, red Exxon…)
and, for everyone else, a tint of their sector's hue.  Tints alternate lighter /
darker within a sector so neighbours in the stack never collapse into one band.

Run this when the list changes:  python pipeline/master_build.py
"""
from __future__ import annotations

import colorsys
import json

from common import ROOT

SECTOR_HUE = {  # muted; checked with the dataviz palette validator for adjacent-band separation
    "NoDur": "#B08A3E", "Durbl": "#8C7B68", "Manuf": "#9AA6B5", "Enrgy": "#A33B34",
    "Chems": "#8E9B4F", "BusEq": "#3F7CA8", "Telcm": "#7A5C94", "Utils": "#2F7F76",
    "Shops": "#D88A32", "Hlth": "#B8677F", "Money": "#2F4468", "Other": "#C2BDB2",
}
BRAND = {  # id -> colour; muted but recognisable
    "apple": "#A9AFB7", "nvidia": "#6C9A3A", "exxon": "#B5382F", "microsoft": "#2F7FA3",
    "alphabet": "#D9A93F", "amazon": "#DE8C2C", "meta": "#4263B8", "tesla": "#E0705F",
    "ibm": "#2B4C8C", "ge": "#5B84B0", "att-corp": "#4E8FC4", "gm": "#7D6A56",
    "walmart": "#7DAAD0", "coca-cola": "#8A2A31", "berkshire": "#8B6B4A", "jpmorgan": "#4A5C75",
    "mobil": "#D9695F", "texaco": "#8E3B2A", "chevron": "#C7783A", "intel": "#3E6FA3",
    "johnson-johnson": "#C25B4E", "procter-gamble": "#5C7AA0", "pfizer": "#4B5FA8",
    "visa": "#27407A", "mastercard": "#C9873A", "netflix": "#9E2A2F", "kodak": "#D3B13C",
    "sears": "#6B7A8F", "dupont": "#B8452F", "us-steel": "#707A86", "citigroup": "#3F6EB5",
    "bank-of-america": "#B04A52", "wells-fargo": "#B8923A", "philip-morris": "#6D8A5C",
    "altria": "#6D8A5C", "pepsico": "#2F5D9B", "disney": "#3E4F8A", "boeing": "#4F7EA5",
    "lilly": "#C0463C", "eli-lilly": "#C0463C", "merck": "#2A7F7A", "broadcom": "#B83A4A",
    "oracle": "#C5483A", "cisco": "#2E7DA6", "hp": "#3C74B0", "verizon": "#C0463C",
    "att": "#2F95C6", "unitedhealth": "#3F6E8C", "home-depot": "#D3772F", "costco": "#B03A3A",
    "time-warner": "#C0577A",
}

# (id, display name, short label, sector, yahoo ticker, CRSP-name regex)
ROWS = [
    # ---- technology
    ("apple", "Apple", "APPLE", "BusEq", "AAPL", r"^APPLE COMPUTER|^APPLE INC"),
    ("microsoft", "Microsoft", "MICROSOFT", "BusEq", "MSFT", r"^MICROSOFT"),
    ("nvidia", "Nvidia", "NVIDIA", "BusEq", "NVDA", r"^NVIDIA"),
    ("alphabet", "Alphabet", "ALPHABET", "BusEq", "GOOGL", r"^GOOGLE|^ALPHABET"),
    ("amazon", "Amazon", "AMAZON", "Shops", "AMZN", r"^AMAZON"),
    ("meta", "Meta Platforms", "META", "BusEq", "META", r"^FACEBOOK|^META PLATFORMS"),
    ("tesla", "Tesla", "TESLA", "Durbl", "TSLA", r"^TESLA"),
    ("broadcom", "Broadcom", "BROADCOM", "BusEq", "AVGO", r"^BROADCOM|^AVAGO"),
    ("oracle", "Oracle", "ORACLE", "BusEq", "ORCL", r"^ORACLE"),
    ("cisco", "Cisco", "CISCO", "BusEq", "CSCO", r"^CISCO"),
    ("intel", "Intel", "INTEL", "BusEq", "INTC", r"^INTEL CORP"),
    ("ibm", "IBM", "IBM", "BusEq", "IBM", r"^INTERNATIONAL BUSINESS MACH|^IBM"),
    ("qualcomm", "Qualcomm", "QUALCOMM", "BusEq", "QCOM", r"^QUALCOMM"),
    ("texas-instruments", "Texas Instruments", "TEXAS INSTR.", "BusEq", "TXN", r"^TEXAS INSTRUMENTS"),
    ("amd", "AMD", "AMD", "BusEq", "AMD", r"^ADVANCED MICRO DEVICES"),
    ("adobe", "Adobe", "ADOBE", "BusEq", "ADBE", r"^ADOBE"),
    ("salesforce", "Salesforce", "SALESFORCE", "BusEq", "CRM", r"^SALESFORCE"),
    ("netflix", "Netflix", "NETFLIX", "Other", "NFLX", r"^NETFLIX"),
    ("hp", "Hewlett-Packard / HP", "HP", "BusEq", "HPQ", r"^HEWLETT PACKARD|^HP INC"),
    ("micron", "Micron", "MICRON", "BusEq", "MU", r"^MICRON TECH"),
    ("applied-materials", "Applied Materials", "APPLIED MAT.", "BusEq", "AMAT", r"^APPLIED MATERIALS"),
    ("palantir", "Palantir", "PALANTIR", "BusEq", "PLTR", r"^PALANTIR"),
    ("dell", "Dell", "DELL", "BusEq", None, r"^DELL COMPUTER|^DELL INC"),
    ("compaq", "Compaq", "COMPAQ", "BusEq", None, r"^COMPAQ"),
    ("dec", "Digital Equipment", "DIGITAL EQ.", "BusEq", None, r"^DIGITAL EQUIPMENT"),
    ("motorola", "Motorola", "MOTOROLA", "BusEq", None, r"^MOTOROLA"),
    ("lucent", "Lucent", "LUCENT", "BusEq", None, r"^LUCENT"),
    ("sun", "Sun Microsystems", "SUN MICRO.", "BusEq", None, r"^SUN MICROSYSTEMS"),
    ("xerox", "Xerox", "XEROX", "BusEq", None, r"^XEROX"),
    ("polaroid", "Polaroid", "POLAROID", "BusEq", None, r"^POLAROID"),
    ("kodak", "Eastman Kodak", "KODAK", "Other", None, r"^EASTMAN KODAK"),
    ("burroughs", "Burroughs / Unisys", "BURROUGHS", "BusEq", None, r"^BURROUGHS|^UNISYS"),
    ("honeywell-old", "Honeywell (old)", "HONEYWELL", "BusEq", None, r"^HONEYWELL INC"),
    # ---- telecom & media
    ("att", "AT&T Inc. (SBC)", "AT&T INC.", "Telcm", "T", r"SOUTHWESTERN BELL|^SBC COMM|AT&T INC"),
    ("att-corp", "AT&T Corp. (Ma Bell)", "AT&T (MA BELL)", "Telcm", None, r"AMERICAN TELEPHONE|^A T & T|^AT&T CORP|^AT&T"),
    ("verizon", "Verizon / Bell Atlantic", "VERIZON", "Telcm", "VZ", r"BELL ATLANTIC|^VERIZON"),
    ("gte", "GTE", "GTE", "Telcm", None, r"^G T E|^GTE|^GENERAL TEL"),
    ("bellsouth", "BellSouth", "BELLSOUTH", "Telcm", None, r"^BELLSOUTH"),
    ("ameritech", "Ameritech", "AMERITECH", "Telcm", None, r"^AMERITECH"),
    ("nynex", "NYNEX", "NYNEX", "Telcm", None, r"^NYNEX"),
    ("us-west", "US West", "US WEST", "Telcm", None, r"^US WEST|^U S WEST"),
    ("pacific-telesis", "Pacific Telesis", "PAC. TELESIS", "Telcm", None, r"^PACIFIC TELESIS"),
    ("mci-worldcom", "MCI / WorldCom", "WORLDCOM", "Telcm", None, r"^WORLDCOM|^MCI"),
    ("comcast", "Comcast", "COMCAST", "Telcm", "CMCSA", r"^COMCAST"),
    ("t-mobile", "T-Mobile US", "T-MOBILE", "Telcm", "TMUS", r"^T MOBILE|^METROPCS"),
    ("disney", "Walt Disney", "DISNEY", "Other", "DIS", r"^DISNEY"),
    ("time-warner", "Time Warner / AOL", "TIME WARNER", "Other", None, r"^TIME WARNER|^AOL|^AMERICA ONLINE"),
    # ---- finance
    ("berkshire", "Berkshire Hathaway", "BERKSHIRE", "Money", "BRK-B", r"^BERKSHIRE HATHAWAY"),
    ("jpmorgan", "JPMorgan Chase", "JPMORGAN", "Money", "JPM", r"JPMORGAN|J P MORGAN CHASE|CHASE MANHATTAN|CHEMICAL BANKING|CHEMICAL NEW YORK"),
    ("jp-morgan-co", "J.P. Morgan & Co.", "J.P. MORGAN", "Money", None, r"^MORGAN J P"),
    ("bank-of-america", "Bank of America", "BANK OF AMERICA", "Money", "BAC", r"^BANK OF AMERICA|NATIONSBANK|^NCNB"),
    ("bankamerica", "BankAmerica", "BANKAMERICA", "Money", None, r"^BANKAMERICA"),
    ("citigroup", "Citigroup", "CITIGROUP", "Money", "C", r"^CITIGROUP|^TRAVELERS GROUP"),
    ("citicorp", "Citicorp", "CITICORP", "Money", None, r"^CITICORP"),
    ("wells-fargo", "Wells Fargo", "WELLS FARGO", "Money", "WFC", r"^WELLS FARGO|^NORWEST"),
    ("goldman-sachs", "Goldman Sachs", "GOLDMAN", "Money", "GS", r"^GOLDMAN SACHS"),
    ("morgan-stanley", "Morgan Stanley", "MORGAN STANLEY", "Money", "MS", r"^MORGAN STANLEY"),
    ("merrill-lynch", "Merrill Lynch", "MERRILL", "Money", None, r"^MERRILL LYNCH"),
    ("lehman", "Lehman Brothers", "LEHMAN", "Money", None, r"^LEHMAN"),
    ("american-express", "American Express", "AMEX", "Money", "AXP", r"^AMERICAN EXPRESS"),
    ("visa", "Visa", "VISA", "Money", "V", r"^VISA INC"),
    ("mastercard", "Mastercard", "MASTERCARD", "Money", "MA", r"^MASTERCARD"),
    ("aig", "AIG", "AIG", "Money", "AIG", r"^AMERICAN INTERNATIONAL GROUP"),
    ("metlife", "MetLife", "METLIFE", "Money", "MET", r"^METLIFE"),
    ("blackrock", "BlackRock", "BLACKROCK", "Money", "BLK", r"^BLACKROCK"),
    ("schwab", "Charles Schwab", "SCHWAB", "Money", "SCHW", r"^SCHWAB"),
    ("fannie-mae", "Fannie Mae", "FANNIE MAE", "Money", None, r"^FEDERAL NATIONAL MORTGAGE"),
    ("freddie-mac", "Freddie Mac", "FREDDIE MAC", "Money", None, r"^FEDERAL HOME LOAN MORTGAGE"),
    ("wachovia", "Wachovia", "WACHOVIA", "Money", None, r"^WACHOVIA"),
    # ---- health
    ("johnson-johnson", "Johnson & Johnson", "J&J", "Hlth", "JNJ", r"^JOHNSON & JOHNSON"),
    ("eli-lilly", "Eli Lilly", "LILLY", "Hlth", "LLY", r"^LILLY ELI"),
    ("merck", "Merck", "MERCK", "Hlth", "MRK", r"^MERCK"),
    ("pfizer", "Pfizer", "PFIZER", "Hlth", "PFE", r"^PFIZER"),
    ("abbvie", "AbbVie", "ABBVIE", "Hlth", "ABBV", r"^ABBVIE"),
    ("abbott", "Abbott", "ABBOTT", "Hlth", "ABT", r"^ABBOTT LABORATORIES"),
    ("bristol-myers", "Bristol-Myers Squibb", "BRISTOL-MYERS", "Hlth", "BMY", r"^BRISTOL MYERS"),
    ("unitedhealth", "UnitedHealth", "UNITEDHEALTH", "Hlth", "UNH", r"^UNITEDHEALTH"),
    ("amgen", "Amgen", "AMGEN", "Hlth", "AMGN", r"^AMGEN"),
    ("thermo-fisher", "Thermo Fisher", "THERMO FISHER", "Hlth", "TMO", r"^THERMO"),
    ("medtronic", "Medtronic", "MEDTRONIC", "Hlth", "MDT", r"^MEDTRONIC"),
    ("gilead", "Gilead", "GILEAD", "Hlth", "GILD", r"^GILEAD"),
    ("wyeth", "Wyeth", "WYETH", "Hlth", None, r"^AMERICAN HOME PRODUCTS|^WYETH"),
    ("schering-plough", "Schering-Plough", "SCHERING", "Hlth", None, r"^SCHERING"),
    ("warner-lambert", "Warner-Lambert", "WARNER-LAMBERT", "Hlth", None, r"^WARNER LAMBERT"),
    ("pharmacia", "Pharmacia / Upjohn", "PHARMACIA", "Hlth", None, r"^PHARMACIA|^UPJOHN"),
    # ---- staples & retail
    ("walmart", "Walmart", "WALMART", "Shops", "WMT", r"^WAL MART|^WALMART"),
    ("procter-gamble", "Procter & Gamble", "P&G", "NoDur", "PG", r"^PROCTER & GAMBLE"),
    ("coca-cola", "Coca-Cola", "COCA-COLA", "NoDur", "KO", r"^COCA COLA CO"),
    ("pepsico", "PepsiCo", "PEPSICO", "NoDur", "PEP", r"^PEPSICO"),
    ("costco", "Costco", "COSTCO", "Shops", "COST", r"^COSTCO"),
    ("philip-morris-intl", "Philip Morris Intl.", "PM INTL.", "NoDur", "PM", r"^PHILIP MORRIS INTERNATIONAL"),
    ("altria", "Philip Morris / Altria", "ALTRIA", "NoDur", "MO", r"^PHILIP MORRIS|^ALTRIA"),
    ("mondelez", "Kraft / Mondelez", "MONDELEZ", "NoDur", "MDLZ", r"^KRAFT|^MONDELEZ"),
    ("colgate", "Colgate-Palmolive", "COLGATE", "NoDur", "CL", r"^COLGATE"),
    ("gillette", "Gillette", "GILLETTE", "NoDur", None, r"^GILLETTE"),
    ("anheuser-busch", "Anheuser-Busch", "ANHEUSER", "NoDur", None, r"^ANHEUSER"),
    ("home-depot", "Home Depot", "HOME DEPOT", "Shops", "HD", r"^HOME DEPOT"),
    ("mcdonalds", "McDonald's", "MCDONALD'S", "Shops", "MCD", r"^MCDONALDS"),
    ("nike", "Nike", "NIKE", "NoDur", "NKE", r"^NIKE"),
    ("lowes", "Lowe's", "LOWE'S", "Shops", "LOW", r"^LOWES"),
    ("starbucks", "Starbucks", "STARBUCKS", "Shops", "SBUX", r"^STARBUCKS"),
    ("sears", "Sears", "SEARS", "Shops", None, r"^SEARS ROEBUCK|^SEARS HOLDINGS|^SEARS INC"),
    ("kmart", "Kmart", "KMART", "Shops", None, r"^KMART|^S S KRESGE"),
    ("woolworth", "Woolworth", "WOOLWORTH", "Shops", None, r"^WOOLWORTH|^F W WOOLWORTH"),
    ("avon", "Avon", "AVON", "NoDur", None, r"^AVON PRODUCTS"),
    # ---- autos & industrials
    ("gm", "General Motors", "GENERAL MOTORS", "Durbl", "GM", r"^GENERAL MOTORS"),
    ("ford", "Ford", "FORD", "Durbl", "F", r"^FORD MOTOR"),
    ("chrysler", "Chrysler", "CHRYSLER", "Durbl", None, r"^CHRYSLER"),
    ("ge", "General Electric", "GENERAL ELECTRIC", "Manuf", "GE", r"^GENERAL ELECTRIC"),
    ("boeing", "Boeing", "BOEING", "Manuf", "BA", r"^BOEING"),
    ("caterpillar", "Caterpillar", "CATERPILLAR", "Manuf", "CAT", r"^CATERPILLAR"),
    ("honeywell", "Honeywell", "HONEYWELL", "Manuf", "HON", r"^ALLIEDSIGNAL|^HONEYWELL INTERNATIONAL"),
    ("union-pacific", "Union Pacific", "UNION PACIFIC", "Other", "UNP", r"^UNION PACIFIC"),
    ("ups", "UPS", "UPS", "Other", "UPS", r"^UNITED PARCEL"),
    ("lockheed", "Lockheed Martin", "LOCKHEED", "Manuf", "LMT", r"^LOCKHEED"),
    ("rtx", "Raytheon / United Tech.", "RTX", "Manuf", "RTX", r"^UNITED TECHNOLOGIES|^RAYTHEON TECH"),
    ("mcdonnell-douglas", "McDonnell Douglas", "MCDONNELL D.", "Manuf", None, r"^MCDONNELL DOUGLAS"),
    ("3m", "3M", "3M", "Manuf", "MMM", r"^MINNESOTA MINING|^3M"),
    ("deere", "Deere", "DEERE", "Manuf", "DE", r"^DEERE"),
    ("us-steel", "U.S. Steel", "U.S. STEEL", "Manuf", None, r"^UNITED STATES STEEL|^USX|^U S STEEL"),
    ("alcoa", "Alcoa", "ALCOA", "Manuf", None, r"^ALUMINUM CO OF AMERICA|^ALCOA"),
    ("tyco", "Tyco", "TYCO", "Manuf", None, r"^TYCO"),
    ("enron", "Enron", "ENRON", "Enrgy", None, r"^ENRON"),
    # ---- energy
    ("exxon", "Exxon (Standard Oil NJ)", "EXXON", "Enrgy", "XOM", r"STANDARD OIL CO N J|^EXXON"),
    ("mobil", "Mobil", "MOBIL", "Enrgy", None, r"^MOBIL CORP|^SOCONY|^STANDARD OIL CO N Y"),
    ("texaco", "Texaco", "TEXACO", "Enrgy", None, r"^TEXACO"),
    ("chevron", "Chevron (Socal)", "CHEVRON", "Enrgy", "CVX", r"STANDARD OIL CO CALIF|^CHEVRON"),
    ("amoco", "Amoco (Standard Oil IN)", "AMOCO", "Enrgy", None, r"STANDARD OIL CO IND|^AMOCO"),
    ("gulf", "Gulf Oil", "GULF", "Enrgy", None, r"^GULF OIL"),
    ("arco", "Atlantic Richfield", "ARCO", "Enrgy", None, r"^ATLANTIC RICHFIELD"),
    ("sohio", "Standard Oil Ohio / BP America", "SOHIO", "Enrgy", None, r"STANDARD OIL CO OH|^SOHIO|^BP AMERICA"),
    ("conoco", "Conoco", "CONOCO", "Enrgy", None, r"^CONOCO INC|^CONTINENTAL OIL"),
    ("conocophillips", "Phillips / ConocoPhillips", "CONOCOPHILLIPS", "Enrgy", "COP", r"^PHILLIPS PETROLEUM|^CONOCOPHILLIPS"),
    ("occidental", "Occidental", "OCCIDENTAL", "Enrgy", "OXY", r"^OCCIDENTAL PETROLEUM"),
    ("slb", "Schlumberger / SLB", "SLB", "Enrgy", "SLB", r"^SCHLUMBERGER|^SLB"),
    ("eog", "EOG Resources", "EOG", "Enrgy", "EOG", r"^EOG RESOURCES"),
    ("halliburton", "Halliburton", "HALLIBURTON", "Enrgy", None, r"^HALLIBURTON"),
    # ---- chemicals & utilities
    ("dupont", "DuPont", "DUPONT", "Chems", None, r"^DU PONT|^DUPONT E I|^E I DU PONT|^DOWDUPONT|^DUPONT DE NEMOURS"),
    ("dow", "Dow", "DOW", "Chems", "DOW", r"^DOW CHEMICAL|^DOW INC"),
    ("union-carbide", "Union Carbide", "UNION CARBIDE", "Chems", None, r"^UNION CARBIDE"),
    ("monsanto", "Monsanto", "MONSANTO", "Chems", None, r"^MONSANTO"),
    ("linde", "Linde / Praxair", "LINDE", "Chems", "LIN", r"^LINDE|^PRAXAIR"),
    ("nextera", "NextEra Energy", "NEXTERA", "Utils", "NEE", r"^NEXTERA|^FLORIDA POWER & LIGHT|^FPL GROUP"),
    ("duke-energy", "Duke Energy", "DUKE", "Utils", "DUK", r"^DUKE ENERGY|^DUKE POWER"),
    ("southern", "Southern Co.", "SOUTHERN", "Utils", "SO", r"^SOUTHERN CO"),
    ("texas-utilities", "Texas Utilities", "TEXAS UTIL.", "Utils", None, r"^TEXAS UTILITIES|^TXU"),
    # ---- former giants and later arrivals (from wrds_unmapped.csv; CRSP writes initials with spaces)
    ("paypal", "PayPal", "PAYPAL", "BusEq", None, r"^PAYPAL"),
    ("danaher", "Danaher", "DANAHER", "Manuf", None, r"DANAHER"),
    ("emc", "EMC", "EMC", "BusEq", None, r"^E M C CORP"),
    ("yahoo", "Yahoo", "YAHOO", "BusEq", None, r"^YAHOO"),
    ("jds-uniphase", "JDS Uniphase", "JDS UNIPHASE", "BusEq", None, r"^J D S UNIPHASE"),
    ("ebay", "eBay", "EBAY", "Shops", None, r"^EBAY"),
    ("genentech", "Genentech", "GENENTECH", "Hlth", None, r"^GENENTECH"),
    ("westinghouse", "Westinghouse", "WESTINGHOUSE", "Manuf", None, r"^WESTINGHOUSE ELECTRIC"),
    ("viacom", "Viacom / Paramount", "PARAMOUNT", "Other", None, r"^VIACOM|^PARAMOUNT|^C B S CORP NEW"),
    ("rjr-nabisco", "Nabisco", "NABISCO", "NoDur", None, r"NABISCO|^NATIONAL BISCUIT"),
    ("waste-management", "Waste Management", "WASTE MGMT.", "Other", None, r"^WASTE MANAGEMENT|^W M X TECH"),
    ("shell-oil", "Shell Oil", "SHELL OIL", "Enrgy", None, r"^SHELL OIL|^SHELL UNION"),
    ("getty", "Getty Oil", "GETTY", "Enrgy", None, r"^GETTY OIL|^PACIFIC WESTN OIL"),
    ("unocal", "Unocal", "UNOCAL", "Enrgy", None, r"^UNION OIL CO CALIF|^UNOCAL"),
    ("sunoco", "Sun Oil / Sunoco", "SUNOCO", "Enrgy", None, r"^SUN INC|^SUN OIL|^SUNOCO"),
    ("tenneco", "Tenneco", "TENNECO", "Enrgy", None, r"^TENNECO|^TENNESSEE GAS"),
    ("marathon", "Marathon Oil", "MARATHON", "Enrgy", None, r"^MARATHON OIL|^OHIO OIL|^TRANSCONTINENTAL OIL"),
    ("superior-oil", "Superior Oil", "SUPERIOR OIL", "Enrgy", None, r"^SUPERIOR OIL"),
    ("cities-service", "Cities Service", "CITIES SERVICE", "Enrgy", None, r"^CITIES SERVICE"),
    ("creole", "Creole Petroleum", "CREOLE", "Enrgy", None, r"^CREOLE PETROLEUM"),
    ("sinclair", "Sinclair Oil", "SINCLAIR", "Enrgy", None, r"^CONSOLIDATED OIL CORP|^SINCLAIR"),
    ("amerada", "Amerada Petroleum", "AMERADA", "Enrgy", None, r"^AMERADA"),
    ("pacific-oil", "Pacific Oil", "PACIFIC OIL", "Enrgy", None, r"^PACIFIC OIL CO"),
    ("pan-american-petroleum", "Pan American Petroleum", "PAN AM. PETROL.", "Enrgy", None, r"^PAN AMERICAN PETROL"),
    ("radioshack", "Tandy / RadioShack", "RADIOSHACK", "Shops", None, r"^TANDY|^RADIOSHACK|^AMERICAN HIDE"),
    ("penney", "J.C. Penney", "J.C. PENNEY", "Shops", None, r"^PENNEY J C|^PENNEY"),
    ("montgomery-ward", "Montgomery Ward / Marcor", "MONTGOMERY WARD", "Shops", None, r"^MARCOR|^MONTGOMERY WARD"),
    ("itt", "ITT", "ITT", "Manuf", None, r"^I T T |^INTERNATIONAL TEL"),
    ("rca", "RCA", "RCA", "BusEq", None, r"^R C A CORP|^RADIO CORP"),
    ("corning", "Corning", "CORNING", "Manuf", None, r"^CORNING"),
    ("weyerhaeuser", "Weyerhaeuser", "WEYERHAEUSER", "Other", None, r"^WEYERHAEUSER"),
    ("georgia-pacific", "Georgia-Pacific", "GEORGIA-PACIFIC", "Other", None, r"^GEORGIA PACIFIC"),
    ("international-paper", "International Paper", "INTL. PAPER", "Other", None, r"^INTERNATIONAL PAPER"),
    ("crown-zellerbach", "Crown Zellerbach", "CROWN ZELLERBACH", "Other", None, r"^CROWN ZELLERBACH"),
    ("smithkline", "SmithKline", "SMITHKLINE", "Hlth", None, r"^SMITH KLINE|^SMITHKLINE"),
    ("sterling-drug", "Sterling Drug", "STERLING DRUG", "Hlth", None, r"^DRUG INC|^STERLING DRUG|^STERLING PRODS"),
    ("pacific-telephone", "Pacific Telephone", "PACIFIC TEL.", "Telcm", None, r"^PACIFIC TELEPHONE"),
    ("general-foods", "General Foods", "GENERAL FOODS", "NoDur", None, r"^GENERAL FOODS|^POSTUM"),
    ("united-fruit", "United Fruit / Chiquita", "UNITED FRUIT", "NoDur", None, r"^UNITED FRUIT|^UNITED BRANDS|^CHIQUITA"),
    ("american-brands", "American Tobacco / American Brands", "AMERICAN BRANDS", "NoDur", None, r"^AMERICAN BRANDS|^AMERICAN TOB|^FORTUNE BRANDS|^BEAM INC"),
    ("liggett", "Liggett & Myers", "LIGGETT", "NoDur", None, r"^LIGGETT"),
    ("schenley", "Schenley", "SCHENLEY", "NoDur", None, r"^SCHENLEY"),
    ("standard-brands", "Standard Brands", "STANDARD BRANDS", "NoDur", None, r"^FLEISCHMANN|^STANDARD BRANDS"),
    ("borden", "Borden", "BORDEN", "NoDur", None, r"^BORDEN"),
    ("bestfoods", "CPC / Bestfoods", "BESTFOODS", "NoDur", None, r"^BESTFOODS|^C P C INTERNATIONAL|^CORN PRODUCTS"),
    ("commonwealth-edison", "Commonwealth Edison", "COMMONWEALTH ED.", "Utils", None, r"^COMMONWEALTH EDISON|^UNICOM"),
    ("pge", "Pacific Gas & Electric", "PG&E", "Utils", None, r"^P G & E|^PACIFIC GAS"),
    ("aep", "American Electric Power", "AEP", "Utils", None, r"^AMERICAN ELECTRIC POWER|^AMERICAN GAS & ELEC"),
    ("con-edison", "Consolidated Edison", "CON EDISON", "Utils", None, r"^CONSOLIDATED EDISON|^CONSOLIDATED GAS CO"),
    ("philadelphia-co", "Philadelphia Co.", "PHILADELPHIA CO.", "Utils", None, r"^PHILADELPHIA CO\b"),
    ("columbia-gas", "Columbia Gas", "COLUMBIA GAS", "Utils", None, r"^COLUMBIA ENERGY|^COLUMBIA GAS"),
    ("ugi", "United Gas Improvement", "UGI", "Utils", None, r"^U G I CORP|^UNITED GAS IMPROVEMENT"),
    ("north-american-co", "North American Co.", "NORTH AMERICAN", "Utils", None, r"^NORTH AMERICAN CO\b"),
    ("public-service", "Public Service Corp.", "PUBLIC SERVICE", "Utils", None, r"^PUBLIC SVC CORP"),
    ("martin-marietta", "Martin Marietta", "MARTIN MARIETTA", "Manuf", None, r"^MARTIN MARIETTA|^MARTIN CO\b|^MARTIN GLENN"),
    ("bethlehem-steel", "Bethlehem Steel", "BETHLEHEM STEEL", "Manuf", None, r"^BETHLEHEM STEEL"),
    ("republic-steel", "Republic Steel", "REPUBLIC STEEL", "Manuf", None, r"^REPUBLIC IRON|^REPUBLIC STEEL"),
    ("kennecott", "Kennecott Copper", "KENNECOTT", "Manuf", None, r"^KENNECOTT"),
    ("anaconda", "Anaconda Copper", "ANACONDA", "Manuf", None, r"^ANACONDA"),
    ("utah-copper", "Utah Copper", "UTAH COPPER", "Manuf", None, r"^UTAH COPPER"),
    ("chile-copper", "Chile Copper", "CHILE COPPER", "Manuf", None, r"^CHILE COPPER"),
    ("kaiser-aluminum", "Kaiser Aluminum", "KAISER ALUMINUM", "Manuf", None, r"^KAISER ALUMINUM"),
    ("international-harvester", "International Harvester", "INTL. HARVESTER", "Manuf", None, r"^INTERNATIONAL HARVESTER|^NAVISTAR"),
    ("american-standard", "American Standard", "AMERICAN STANDARD", "Manuf", None, r"^AMERICAN RADIATOR|^AMERICAN STANDARD"),
    ("american-can", "American Can / Primerica", "AMERICAN CAN", "Manuf", None, r"^AMERICAN CAN|^PRIMERICA"),
    ("continental-can", "Continental Can", "CONTINENTAL CAN", "Manuf", None, r"^CONTINENTAL CAN|^CONTINENTAL GROUP"),
    ("pullman", "Pullman", "PULLMAN", "Manuf", None, r"^PULLMAN"),
    ("goodyear", "Goodyear", "GOODYEAR", "Durbl", None, r"^GOODYEAR"),
    ("firestone", "Firestone", "FIRESTONE", "Durbl", None, r"^FIRESTONE"),
    ("studebaker", "Studebaker-Packard", "STUDEBAKER", "Durbl", None, r"^PACKARD MTR|^STUDEBAKER"),
    ("fisher-body", "Fisher Body", "FISHER BODY", "Durbl", None, r"^FISHER BODY"),
    ("national-lead", "National Lead", "NATIONAL LEAD", "Chems", None, r"^N L INDUSTRIES|^NATIONAL LEAD"),
    ("american-cyanamid", "American Cyanamid", "CYANAMID", "Chems", None, r"^AMERICAN CYANAMID"),
    ("ppg", "PPG", "PPG", "Chems", None, r"^P P G INDUSTRIES|^PITTSBURGH PLATE"),
    ("penn-central", "Pennsylvania Railroad / Penn Central", "PENN CENTRAL", "Other", None, r"^PENN CENTRAL|^PENNSYLVANIA RAILROAD|^PENNSYLVANIA NEW YORK"),
    ("new-york-central", "New York Central", "NY CENTRAL", "Other", None, r"^NEW YORK CENT"),
    ("atchison", "Santa Fe Railway", "SANTA FE", "Other", None, r"^ATCHISON"),
    ("chesapeake-ohio", "Chesapeake & Ohio", "C&O", "Other", None, r"^CHESAPEAKE & OHIO|^CHESSIE"),
    ("southern-pacific", "Southern Pacific", "SOUTHERN PACIFIC", "Other", None, r"^SOUTHERN PACIFIC"),
    ("norfolk-western", "Norfolk & Western", "NORFOLK & WESTERN", "Other", None, r"^NORFOLK & WESTERN"),
    ("delaware-lackawanna", "Delaware, Lackawanna & Western", "DL&W", "Other", None, r"^DELAWARE LACK"),
    ("interco", "Interco", "INTERCO", "Other", None, r"^FURNITURE BRANDS|^INTERCO"),
    ("national-city-bank", "National City Bank NY", "NATIONAL CITY", "Money", None, r"^NATIONAL CITY BK"),
    ("transamerica", "Transamerica", "TRANSAMERICA", "Money", None, r"^TRANSAMERICA"),
    ("united-corp", "United Corp.", "UNITED CORP.", "Money", None, r"^UNITED CORP\b"),
]


def hex_to_hls(h: str):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def hls_to_hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def main() -> None:
    seen: dict[str, int] = {}
    out = []
    offsets = [0.0, 0.13, -0.10, 0.24, -0.17, 0.06, -0.06, 0.18]
    for cid, name, short, sector, yahoo, match in ROWS:
        k = seen.get(sector, 0)
        seen[sector] = k + 1
        if cid in BRAND:
            color = BRAND[cid]
        else:
            h, l, s = hex_to_hls(SECTOR_HUE[sector])
            color = hls_to_hex(h, min(0.68, l + offsets[k % len(offsets)]), s * (0.95 - 0.04 * (k % 3)))   # never near-white
        out.append({"id": cid, "name": name, "short": short, "sector": sector,
                    "color": color, "yahoo": yahoo, "match": match})
    ids = [o["id"] for o in out]
    assert len(ids) == len(set(ids)), "duplicate ids"
    (ROOT / "data" / "companies.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    free = {l.split(",")[0] for l in (ROOT / "pipeline" / "universe_free.csv").read_text().splitlines()[1:]}
    missing = sorted(free - set(ids))
    print(f"{len(out)} companies written; free-tier ids missing from master: {missing}")


if __name__ == "__main__":
    main()
