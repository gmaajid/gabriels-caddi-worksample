# Supply Chain Procurement Concepts

## Table of Contents

- [Key Metrics](#key-metrics)
  - [Supplier Performance](#supplier-performance)
  - [Procurement Efficiency](#procurement-efficiency)
- [RFQ (Request for Quotation) Process](#rfq-request-for-quotation-process)
- [Quality Inspection Flow](#quality-inspection-flow)
- [Supplier Consolidation](#supplier-consolidation)
- [CADDi Drawer](#caddi-drawer)

## Key Metrics

### Supplier Performance
- **On-Time Delivery Rate**: % of orders delivered by promised_date. Late = actual_delivery_date > promised_date.
- **Quality Rejection Rate**: parts_rejected / parts_inspected per supplier
- **Price Competitiveness**: supplier's quote vs average quote for same part in RFQ
- **Lead Time**: weeks from order to delivery, or quoted lead_time_weeks in RFQ

### Procurement Efficiency
- **Cost Variance**: difference between quoted price and actual unit_price paid
- **Sole Source Risk**: parts with only one qualified supplier
- **Spend Concentration**: % of total spend with each supplier

## RFQ (Request for Quotation) Process
1. Buyer issues RFQ for a specific part
2. Multiple suppliers respond with quotes (price, lead time, notes)
3. Buyer evaluates responses on price, lead time, quality history, reliability
4. Best supplier selected and purchase order issued

## Quality Inspection Flow
1. Goods received from supplier
2. Incoming inspection performed (sample or 100%)
3. Parts classified: passed, rejected (with reason), rework required
4. Rejection reasons tracked: surface finish, machining marks, calibration, shipping damage, etc.

## Supplier Consolidation
When multiple name variants refer to the same supplier, they must be normalized for accurate analytics. Common patterns: abbreviations (Mfg vs Manufacturing), case differences, Inc/LLC suffixes.

## CADDi Drawer
CADDi Drawer is a SaaS product that helps manufacturers manage drawings and supply chain data. It uses AI to:
- Search and find similar past drawings
- Reference past order history for similar parts
- Identify cost reduction opportunities
- Standardize supplier and part information
