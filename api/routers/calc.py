# api/routers/calc.py
# Endpoint REST para el motor de cálculo de ingeniería eléctrica/electrónica.

import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from tools.electrical_formulas import FORMULA_REGISTRY
from database.component_stock import get_stock_db

router = APIRouter(prefix="/api/calc", tags=["calc"])


class CalcRequest(BaseModel):
    formula: str
    params:  dict[str, Any] = {}


class CalcResponse(BaseModel):
    formula:     str
    result:      dict[str, Any]
    stock_match: dict[str, Any] | None = None


@router.post("/compute", response_model=CalcResponse)
def compute(req: CalcRequest):
    """
    Ejecuta una fórmula de ingeniería con los parámetros dados.

    Ejemplo:
        POST /api/calc/compute
        {"formula": "resistor_for_led", "params": {"vcc": 5, "vled": 2.0, "iled_ma": 20}}
    """
    if req.formula not in FORMULA_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Fórmula '{req.formula}' no encontrada. "
                   f"Disponibles: {list(FORMULA_REGISTRY.keys())}"
        )

    try:
        fn = FORMULA_REGISTRY[req.formula]
        result = fn(**req.params)
    except TypeError as e:
        raise HTTPException(status_code=422, detail=f"Parámetros inválidos: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de cálculo: {e}")

    # Buscar en stock si hay un valor estándar
    stock_match = None
    std_val = result.get("std_value")
    if std_val:
        try:
            cat_map = {
                "resistor_for_led":          "resistencia",
                "resistor_voltage_divider":  "resistencia",
                "resistor_power":            "resistencia",
                "capacitor_filter":          "capacitor",
                "low_pass_rc":               "capacitor",
                "rc_time_constant":          "capacitor",
                "high_pass_rc":              "resistencia",
                "buck_converter":            "inductor",
                "boost_converter":           "inductor",
                "fuse_rating":               "fusible",
            }
            category = cat_map.get(req.formula, "")
            if category:
                items = get_stock_db().search_components(category) or []
                if items:
                    def parse_val(item):
                        s = str(item.get("value", "0")).replace(",", ".").strip()
                        m = re.search(r'[\d.]+', s)
                        return float(m.group()) if m else 0.0
                    closest = min(items, key=lambda x: abs(parse_val(x) - float(std_val)))
                    stock_match = {
                        "name":     closest.get("name"),
                        "value":    closest.get("value"),
                        "quantity": closest.get("quantity"),
                        "category": closest.get("category"),
                        "package":  closest.get("package"),
                    }
        except Exception:
            pass

    return CalcResponse(formula=req.formula, result=result, stock_match=stock_match)


@router.get("/formulas")
def list_formulas():
    """Lista todas las fórmulas disponibles con descripción."""
    descriptions = {
        "resistor_for_led":          "Resistencia limitadora para LED (Vcc, Vled, Iled)",
        "resistor_voltage_divider":  "Divisor de tensión resistivo (Vin, Vout, R1)",
        "resistor_power":            "Potencia disipada en resistencia (R, I o V)",
        "capacitor_filter":          "Capacitor para filtro RC paso bajo (f, R)",
        "rc_time_constant":          "Constante de tiempo RC (R, C)",
        "capacitor_energy":          "Energía almacenada en capacitor (C, V)",
        "power_dissipation":         "Potencia disipada P=V×I (V, I)",
        "heat_sink_required":        "Resistencia térmica disipador requerida (P, Ta, θjc)",
        "efficiency":                "Eficiencia energética (Pout, Pin)",
        "fuse_rating":               "Fusible recomendado (Imax, factor seguridad)",
        "buck_converter":            "Convertidor BUCK: L y C (Vin, Vout, Iout, freq)",
        "boost_converter":           "Convertidor BOOST: L y C (Vin, Vout, Iout, freq)",
        "transformer_turns_ratio":   "Relación de transformación (Vp, Vs)",
        "low_pass_rc":               "Filtro paso bajo RC: C (fc, R)",
        "high_pass_rc":              "Filtro paso alto RC: R (fc, C)",
        "lc_filter":                 "Filtro LC 2do orden: L y C (fc, Z)",
        "inverting_amp":             "Amplificador inversor: ganancia (Rin, Rf)",
        "non_inverting_amp":         "Amplificador no inversor: ganancia (R1, R2)",
        "voltage_follower":          "Buffer/seguidor de tensión (sin parámetros)",
        "battery_autonomy":          "Autonomía de batería en horas (mAh, mA)",
        "charge_time":               "Tiempo de carga de batería (mAh, Icarga)",
        "motor_power":               "Potencia mecánica de motor (V, I, η)",
        "vfd_frequency_for_rpm":     "Frecuencia VFD para RPM de motor AC (rpm, polos)",
        "motor_torque":              "Torque de motor (P, rpm)",
        "ohms_law":                  "Ley de Ohm — calcula el parámetro faltante (V, I, R)",
    }
    return {
        "formulas": [
            {"key": k, "description": descriptions.get(k, k)}
            for k in FORMULA_REGISTRY
        ]
    }
