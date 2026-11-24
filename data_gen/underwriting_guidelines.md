# PremiumPulse Auto Insurance Underwriting Guidelines & Rating Manual

## Section 1: Telematics Program Enrollment & Data Requirements

### [UG-101] Mandatory Telematics Window
All policyholders enrolled in the PremiumPulse usage-based rating plan are evaluated over a rolling 30-day telematics window. Telematics data is captured continuously during active trips and aggregated at the close of each billing cycle to compute renewal quotes.

### [UG-102] Minimum Driving Distance Threshold
To qualify for a performance-based telematics score, a driver must record a minimum of 50.0 cumulative kilometers within the 30-day assessment window. Drivers recording fewer than 50.0 kilometers are designated as `UNRATED` and receive a standard band multiplier of 1.00 with zero telematics penalty or discount applied.

## Section 2: Scorecard Methodology & Penalties

### [UG-103] Scorecard v1 Deductions
The telematics scorecard operates on a 100-point baseline. Points are deducted based on six monitored risk factors using the formula `penalty = weight * min(metric / cap, 1.0)`:
- Hard Braking: Weight 25 points, cap 15 events per 100 km (deceleration <= -3.0 m/s^2).
- Speeding: Weight 25 points, cap 20% of driving time exceeding speed limit by >10 km/h.
- Distracted Phone Use: Weight 20 points, cap 30 minutes per 100 km while vehicle is in motion.
- Night Driving: Weight 15 points, cap 25% of driving time between midnight (00:00) and 04:00 AM.
- Hard Acceleration: Weight 10 points, cap 12 events per 100 km (acceleration >= +3.0 m/s^2).
- Mileage Exposure: Weight 5 points, cap 3,000 kilometers per 30-day period.

### [UG-104] Risk Band Classifications
Final telematics scores are rounded to one decimal place and categorized into five risk bands:
- Band A (Score 85.0 to 100.0): Exceptional driver, qualifying for a 20% discount (0.80 multiplier).
- Band B (Score 70.0 to 84.9): Safe driver, qualifying for a 5% discount (0.95 multiplier).
- Band C (Score 55.0 to 69.9): Standard risk, carrying a 10% surcharge (1.10 multiplier).
- Band D (Score 40.0 to 54.9): Elevated risk, carrying a 35% surcharge (1.35 multiplier).
- Band E (Score 0.0 to 39.9): High risk, carrying a 70% surcharge (1.70 multiplier).

## Section 3: Actuarial Rating Factors & Premium Calculation

### [UG-105] Vehicle Base Rates
Monthly baseline premiums depend strictly on the certified vehicle classification:
- Hatchback: $38.00 base rate.
- Sedan: $45.00 base rate.
- SUV: $55.00 base rate.
- Electric Vehicle (EV): $52.00 base rate.
- Pickup Truck: $58.00 base rate.

### [UG-106] Annual Mileage Tiers
Declared annual mileage is verified and scaled according to four actuarial tiers:
- Tier 1 (Up to 8,000 km): Low mileage credit, 0.92 multiplier.
- Tier 2 (8,001 to 15,000 km): Standard commuter baseline, 1.00 multiplier.
- Tier 3 (15,001 to 25,000 km): Elevated usage, 1.12 multiplier.
- Tier 4 (Over 25,000 km): High exposure / commercial usage, 1.25 multiplier.

### [UG-107] Vehicle Age and Driver Experience Factors
Premiums incorporate vehicle mechanical reliability and driver experience:
- Vehicle Age: <= 3 years applies 1.05 multiplier (replacement cost); 4 to 8 years applies 1.00 multiplier; > 8 years applies 1.08 multiplier (wear and safety feature degradation).
- Driver Licence Experience: <= 2 years applies 1.25 multiplier (novice driver); 3 to 5 years applies 1.10 multiplier; > 5 years applies 1.00 multiplier.

### [UG-108] Statutory Premium Clamping
The total monthly premium is calculated as the multiplicative product of Base Rate, Band Multiplier, Mileage Factor, Vehicle Age Factor, and Experience Factor. To preserve regulatory compliance and market viability, the resulting monthly premium is strictly clamped between a minimum of $25.00 and a maximum of $220.00.

## Section 4: Privacy, Governance, and Exclusions

### [UG-109] Protected Attribute Non-Discrimination
In accordance with fair insurance regulations, pricing and scoring models must never utilize protected personal attributes. Driver name, email address, postal code, city, and driver age band are strictly prohibited from entering the rating calculation. Premium differentials are driven solely by vehicle class, driver licence tenure, annual distance, vehicle age, and verified driving behavior.

### [UG-110] Monthly Quote Adjustments and Policy Renewals
Dynamic quotes are regenerated at the end of each billing cycle using the updated 30-day driving record. Policyholders who improve their telematics risk band will see premium discounts automatically applied on their subsequent monthly invoice.
