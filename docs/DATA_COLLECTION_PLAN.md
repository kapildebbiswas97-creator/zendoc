# ZENDOC Official/Public Data + Data-Gap Collection Plan

**Branch:** `post-submission-production`  
**Purpose:** define what ZENDOC can collect now at zero capital, what needs provider/patient surveys, what requires authorized partner access, and what should wait for funded field verification.

## 1. Official/public data we can work with now

### National hospital directory
Source: Open Government Data Platform India.

Use for:
- hospital/facility name;
- address/city/district/state;
- geolocation where supplied;
- public contact fields;
- public facility category/specialty metadata.

Do not treat a directory row as:
- live appointment availability;
- current bed availability;
- ZENDOC verification;
- ZENDOC booking connectivity.

Recommended connector:
- configured data.gov.in resource API/download;
- monthly refresh;
- resource ID and API key supplied through environment configuration.

### Local Government Directory (LGD)
Source: Ministry of Panchayati Raj / official government datasets.

Use for:
- state/district/block/local-body/village hierarchy;
- official codes;
- geography graph normalization;
- district/block/village-level pilot coverage analysis.

Recommended connector:
- configured official resource/download;
- monthly refresh;
- preserve LGD source code and snapshot date.

### Blood-bank directory
Source: official government open-data/public directory.

Use for:
- blood-centre identity;
- location;
- public contact metadata.

Do not convert a static directory into current blood-stock availability.

Dynamic blood availability remains a high-freshness operational data gap.

### West Bengal Health Scheme empanelled HCO directory
Source: Finance Department, Government of West Bengal.

Use for the West Bengal pilot:
- hospital code;
- hospital/HCO name;
- address;
- class;
- validity;
- facilities where published.

Use a dated official download/search snapshot.

Do not infer:
- general-public eligibility;
- current beds;
- current appointment slots;
- live scheme authorization.

### Other registered official sources already tracked by ZENDOC

The registry also separates:
- ABDM HFR;
- ABDM HPR;
- NMC registration lookup;
- NABH;
- NABL;
- Clinical Establishments Register;
- PM-JAY provider discovery;
- Swasthya Sathi hospitals;
- CGHS hospitals;
- Jan Aushadhi Kendras/product references;
- NPPA price references;
- CDSCO/NLEM;
- e-RaktKosh;
- myScheme;
- nursing/pharmacy/medical-education directories.

Where no verified stable bulk API exists, ZENDOC should use a dated manual/configured snapshot rather than scraping a website and pretending the integration is stable.

## 2. P0 data to collect now with zero capital

These have the highest pilot value.

### Pharmacy inventory
Collect manually during pilot or through future POS integration.

Minimum fields:
- pharmacy ID;
- medicine SKU;
- quantity available;
- stock state;
- observed timestamp.

### Pharmacy actual price
Minimum fields:
- pharmacy ID;
- SKU;
- selling price;
- discount;
- observed timestamp.

Public MRP/reference data is not a replacement for actual provider selling price.

### Lab/diagnostic offers
Minimum fields:
- lab ID;
- test ID;
- price;
- home-collection fee;
- observed timestamp.

### Lab slots
Minimum fields:
- lab ID;
- test ID;
- date;
- slot start/end;
- confirmation timestamp.

### Doctor live slots
Minimum fields:
- provider ID;
- date;
- slot start/end;
- consultation type;
- confirmation timestamp.

### Provider response time
No survey needed.

Measure automatically inside ZENDOC from:
- request created time;
- first real provider acknowledgement/response time;
- provider;
- workflow type.

### Health Memory records
For pilot:
- patient-consented upload;
- authorized provider workflow when available.

Only collect fields needed for the patient-authorized care purpose.

## 3. P1 survey data worth collecting

### Provider survey
Collect:
- service/delivery radius;
- languages;
- payment modes;
- opening/service hours;
- approximate queue/wait state where operationally maintained;
- wheelchair/lift/accessibility facts;
- home collection/home care support.

Avoid vague fields such as "best hospital" or unsupported quality scores.

### Patient-experience survey
Prefer interaction-linked or anonymous/consented surveys.

Useful fields:
- travel-time band;
- cost barrier band;
- language barrier;
- digital-access barrier;
- wait-time experience;
- medicine unavailability category;
- diagnostic delay category/reason.

Do not ask for diagnosis, full prescriptions, claim documents, or identity when aggregate access-barrier data is sufficient.

## 4. Data that requires a real authorized partner

Do not simulate these.

### Ambulance dispatch
Requires:
- dispatcher/ambulance partner;
- real dispatch status;
- ETA;
- confirmed timestamp.

### Live hospital/ICU bed availability
Requires:
- hospital or authorized government feed;
- timestamped bed type/count;
- authoritative source.

Static capacity must never be represented as current vacancy.

### Scheme eligibility/approval/payment
Requires:
- government/insurer/authority response;
- authoritative evidence type;
- reference ID;
- confirmation timestamp.

### Claims and insurance
Requires:
- insurer/TPA/authorized workflow or user-consented evidence.

No public scraping.

### ABDM/HFR/HPR production integration
Requires the appropriate onboarding/authorization before ZENDOC can claim live registry connectivity.

## 5. Data to defer until funding or stronger partnerships

Funding can improve:
- field verification of accessibility;
- large provider onboarding drives;
- provider device/POS integration;
- partner SLA monitoring;
- high-frequency local medicine availability;
- hospital capacity integration;
- large patient-access surveys;
- professional data-quality verification teams.

Funding must improve validation and coverage; it should not change ZENDOC's truthfulness rules.

## 6. Collection priority

### Priority 0
1. pharmacy stock;
2. pharmacy actual selling price;
3. diagnostic offers;
4. diagnostic slots;
5. doctor slots;
6. provider response time;
7. consented Health Memory.

### Priority 1
1. service radius;
2. provider languages;
3. payment modes;
4. care-access barriers;
5. patient interaction satisfaction;
6. medicine access gaps;
7. diagnostic delays;
8. scheme outcome evidence when available.

### Priority 2
1. field-verified accessibility;
2. claims/insurance integration;
3. scaled provider verification.

## 7. Operational rules

Every external record should carry:
- source ID;
- source record/reference ID;
- source trust state;
- freshness timestamp;
- ingestion/apply timestamp;
- verification state;
- ZENDOC connectivity state.

ZENDOC must preserve these distinctions:

- official/public directory record;
- ZENDOC-verified provider;
- live provider observation;
- connected partner;
- user-submitted evidence;
- authoritative external confirmation.

These states are not interchangeable.

## 8. Founder pilot action

For an initial local West Bengal pilot, the best no-capital data strategy is:

1. ingest official geography and hospital/provider directories;
2. select a small pilot geography rather than India-wide manual collection;
3. onboard a small number of pharmacies/labs/doctors manually;
4. collect live stock/price/slots through provider refresh workflows;
5. collect provider languages/service radius/payment/accessibility;
6. measure response times automatically;
7. gather anonymous/consented care-barrier feedback;
8. record every unavailable field in the data-gap registry rather than inventing it.

This produces a small but truthful live dataset that is more valuable for a pilot than a large unverified directory.
