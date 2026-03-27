"""Pydantic models for Hoth Industries supply chain data."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field, model_validator


# --- Enums ---

class RejectionSeverity(str, Enum):
    """Rejection reasons grouped by severity."""
    PASSED = "passed"
    COSMETIC = "cosmetic"           # surface scratches, paint chips, cosmetic only, minor cosmetic
    MACHINING = "machining"         # burrs, machining marks, surface finish issues
    CALIBRATION = "calibration"     # calibration, sensor drift, balance issues
    STRUCTURAL = "structural"       # welding, tube spacing, thickness, alloy, leaks
    SHIPPING = "shipping"           # blade damage in shipping


REJECTION_SEVERITY_MAP: dict[str, RejectionSeverity] = {
    "Passed": RejectionSeverity.PASSED,
    "Cosmetic only": RejectionSeverity.COSMETIC,
    "Minor cosmetic": RejectionSeverity.COSMETIC,
    "Surface scratches": RejectionSeverity.COSMETIC,
    "Paint chips": RejectionSeverity.COSMETIC,
    "Minor surface finish issues": RejectionSeverity.MACHINING,
    "Minor machining marks": RejectionSeverity.MACHINING,
    "Burrs on edges": RejectionSeverity.MACHINING,
    "Calibration slightly off": RejectionSeverity.CALIBRATION,
    "Sensor drift": RejectionSeverity.CALIBRATION,
    "Balance issues": RejectionSeverity.CALIBRATION,
    "Welding defects multiple tubes": RejectionSeverity.STRUCTURAL,
    "Poor weld quality": RejectionSeverity.STRUCTURAL,
    "Wrong alloy used": RejectionSeverity.STRUCTURAL,
    "Material grade wrong": RejectionSeverity.STRUCTURAL,
    "Tube spacing incorrect": RejectionSeverity.STRUCTURAL,
    "Tube alignment poor": RejectionSeverity.STRUCTURAL,
    "Wrong thickness - too thin": RejectionSeverity.STRUCTURAL,
    "Coil spacing wrong": RejectionSeverity.STRUCTURAL,
    "Leaked during pressure test": RejectionSeverity.STRUCTURAL,
    "Blade damage in shipping": RejectionSeverity.SHIPPING,
}


# --- Supplier Normalization ---
#
# Uses hybrid clustering (Jaccard + embedding) from supplier_clustering.py.
# On first use, clusters are built from all raw names found in the CSVs.
# The lookup table is then cached for the lifetime of the process.
#
# The hybrid approach:
# - Jaccard handles abbreviations (MFG -> Manufacturing)
# - Embeddings handle typos and semantic similarity
# - Combined score separates "APEX MFG" from "APEX Farms"

from src.supplier_clustering import (  # noqa: E402
    ClusterMethod,
    build_normalizer,
    tokenize_company,
)

# Module-level cache: populated lazily by init_supplier_normalizer()
_supplier_lookup: dict[str, str] = {}
_supplier_clusters: dict[str, list[str]] = {}


def init_supplier_normalizer(
    raw_names: list[str],
    method: ClusterMethod = ClusterMethod.HYBRID,
    **kwargs,
) -> None:
    """Build the supplier normalization lookup from a list of raw names.

    Call this once after loading CSVs. Until called, normalize_supplier()
    falls back to tokenize-and-title-case.
    """
    global _supplier_lookup, _supplier_clusters
    _supplier_lookup, _supplier_clusters = build_normalizer(raw_names, method=method, **kwargs)


def get_supplier_clusters() -> dict[str, list[str]]:
    """Return the current cluster mapping (canonical -> variants)."""
    return dict(_supplier_clusters)


def normalize_supplier(raw_name: str) -> str:
    """Map a raw supplier name to its canonical clustered form.

    If the normalizer has been initialized (via init_supplier_normalizer),
    uses the precomputed lookup table. Otherwise falls back to
    tokenize -> title-case (lossy but deterministic).
    """
    stripped = raw_name.strip()
    if _supplier_lookup:
        return _supplier_lookup.get(stripped, stripped)
    # Fallback: title-case the expanded tokens
    tokens = tokenize_company(stripped)
    return " ".join(t.title() for t in sorted(tokens)) if tokens else stripped


# --- Core Models ---

class Supplier(BaseModel):
    """Normalized supplier entity."""
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)


class SupplierOrder(BaseModel):
    """A purchase order line item."""
    order_id: str = Field(description="PO number, e.g. PO-2021-011")
    supplier_name_raw: str = Field(description="Original supplier name from CSV (messy)")
    part_number: str = Field(description="Part number, e.g. CTRL-9998")
    part_description: str
    order_date: date
    promised_date: date
    actual_delivery_date: Optional[date] = Field(
        default=None,
        description="Null for orders not yet delivered (8 rows in PO-2025-501)",
    )
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)
    po_amount: float = Field(gt=0)

    @computed_field
    @property
    def supplier_name(self) -> str:
        return normalize_supplier(self.supplier_name_raw)

    @computed_field
    @property
    def days_late(self) -> Optional[int]:
        if self.actual_delivery_date is None:
            return None
        delta = (self.actual_delivery_date - self.promised_date).days
        return delta if delta > 0 else 0

    @computed_field
    @property
    def is_late(self) -> Optional[bool]:
        if self.days_late is None:
            return None
        return self.days_late > 0


class QualityInspection(BaseModel):
    """An incoming quality inspection record."""
    inspection_id: str = Field(description="e.g. INS-110")
    order_id: str = Field(description="FK to SupplierOrder.order_id")
    inspection_date: date
    parts_inspected: int = Field(ge=0)
    parts_rejected: int = Field(ge=0)
    rejection_reason: str
    rework_required: bool

    @computed_field
    @property
    def rejection_rate(self) -> float:
        if self.parts_inspected == 0:
            return 0.0
        return self.parts_rejected / self.parts_inspected

    @computed_field
    @property
    def severity(self) -> RejectionSeverity:
        return REJECTION_SEVERITY_MAP.get(self.rejection_reason, RejectionSeverity.COSMETIC)

    @model_validator(mode="after")
    def rejected_lte_inspected(self):
        if self.parts_rejected > self.parts_inspected:
            raise ValueError("parts_rejected cannot exceed parts_inspected")
        return self


class RFQResponse(BaseModel):
    """A supplier's quote in response to an RFQ.

    RFQ-to-PO mapping: RFQs map 1:1 to POs by sequential sort order.
    RFQ-2021-001 -> PO-2021-011, RFQ-2021-002 -> PO-2021-021, etc.
    Each RFQ represents a competitively-quoted line item within a larger PO.
    RFQ quote_date always falls within the PO's order_date range.
    Part descriptions differ between RFQ and PO (e.g. "Temperature Controller"
    vs "Touch Screen Controller") but the temporal and supplier alignment confirms
    the mapping.
    """
    rfq_id: str = Field(description="e.g. RFQ-2021-001")
    supplier_name_raw: str = Field(description="Original supplier name from CSV")
    part_description: str
    quote_date: date
    quoted_price: float = Field(gt=0)
    lead_time_weeks: int = Field(ge=0)
    notes: Optional[str] = None

    @computed_field
    @property
    def supplier_name(self) -> str:
        return normalize_supplier(self.supplier_name_raw)


# --- RFQ-to-PO Mapping ---

def build_rfq_to_po_map(
    rfq_ids: list[str], order_ids: list[str]
) -> dict[str, str]:
    """Map RFQ IDs to PO IDs by sequential sort order.

    RFQs and POs have a 1:1 correspondence when both lists are sorted.
    45 RFQs map to the first 45 of 48 POs. The last 3 POs had no RFQ.
    """
    rfq_sorted = sorted(set(rfq_ids))
    po_sorted = sorted(set(order_ids))
    return {rfq: po for rfq, po in zip(rfq_sorted, po_sorted)}


# --- Loader Helpers ---

def load_orders_from_csv(path: str) -> list[SupplierOrder]:
    """Parse supplier_orders.csv into validated models."""
    import pandas as pd
    df = pd.read_csv(path)
    orders = []
    for _, row in df.iterrows():
        orders.append(SupplierOrder(
            order_id=row["order_id"],
            supplier_name_raw=row["supplier_name"],
            part_number=row["part_number"],
            part_description=row["part_description"],
            order_date=row["order_date"],
            promised_date=row["promised_date"],
            actual_delivery_date=row["actual_delivery_date"] if pd.notna(row["actual_delivery_date"]) else None,
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            po_amount=row["po_amount"],
        ))
    return orders


def load_inspections_from_csv(path: str) -> list[QualityInspection]:
    """Parse quality_inspections.csv into validated models."""
    import pandas as pd
    df = pd.read_csv(path)
    inspections = []
    for _, row in df.iterrows():
        inspections.append(QualityInspection(
            inspection_id=row["inspection_id"],
            order_id=row["order_id"],
            inspection_date=row["inspection_date"],
            parts_inspected=row["parts_inspected"],
            parts_rejected=row["parts_rejected"],
            rejection_reason=row["rejection_reason"],
            rework_required=row["rework_required"] == "Yes",
        ))
    return inspections


def load_rfq_from_csv(path: str) -> list[RFQResponse]:
    """Parse rfq_responses.csv into validated models."""
    import pandas as pd
    df = pd.read_csv(path)
    responses = []
    for _, row in df.iterrows():
        responses.append(RFQResponse(
            rfq_id=row["rfq_id"],
            supplier_name_raw=row["supplier_name"],
            part_description=row["part_description"],
            quote_date=row["quote_date"],
            quoted_price=row["quoted_price"],
            lead_time_weeks=row["lead_time_weeks"],
            notes=row.get("notes"),
        ))
    return responses
