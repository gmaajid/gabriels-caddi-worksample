# Hoth Industries - Company Context

## Table of Contents

- [Key Business Challenges](#key-business-challenges)
- [Product Domain](#product-domain)
- [Supplier Ecosystem](#supplier-ecosystem)
- [Data Quality Issues](#data-quality-issues)

Hoth Industries manufactures air handling and cooling products for data centers.

## Key Business Challenges
- Managing a complex supply chain with multiple suppliers for similar parts
- Supplier name inconsistencies in records (e.g., "Apex Mfg", "APEX MFG", "Apex Manufacturing Inc" are the same supplier)
- Quality control across diverse supplier base
- Balancing cost vs lead time vs quality when selecting suppliers
- Tracking delivery performance (on-time vs late deliveries)

## Product Domain
- Heat exchangers (copper, aluminum, various sizes)
- Fans and fan motors (axial fans, high CFM fans, motor assemblies)
- Control systems (PLCs, VFDs, temperature controllers, touch screen controllers)
- Sensors (temperature probes, humidity sensors, flow sensors)
- Filters (HEPA industrial filters)
- Structural components (brackets, panels, enclosures, shafts, dampers)
- Thermal components (fins, bearings, vibration mounts)

## Supplier Ecosystem
Known suppliers include:
- AeroFlow Systems
- Precision Thermal Co
- Stellar Metalworks
- Apex Manufacturing Inc (also: Apex Mfg, APEX MFG, APEX Manufacturing Inc)
- TitanForge LLC
- QuickFab Industries

## Data Quality Issues
- Supplier names are inconsistent across records (case, abbreviation, spelling)
- Some delivery dates may be missing
- Quality inspection data links to orders via order_id
- RFQ responses link to orders via part descriptions (not exact matching)
