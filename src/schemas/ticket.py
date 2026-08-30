"""Pydantic CompraIn — validación centralizada (cédula 9-12, teléfono, ubicacion, mesa 1..12, monto)"""
import re
from pydantic import BaseModel, Field, field_validator

class CompraIn(BaseModel):
    nombre_completo: str = Field(min_length=1, max_length=80)
    cedula: str
    ubicacion: str = Field(pattern="^(Gradas|Mesas)$")
    mesa_numero: int | None = Field(None, ge=1, le=12)
    telefono: str  # validado en field_validator, sin pattern para aceptar 88888888 y +50688888888
    monto: int | None = None

    @field_validator("cedula")
    def cedula_cr(cls, v):
        d = re.sub(r"\D", "", v)
        if not 9 <= len(d) <= 12:
            raise ValueError("cédula 9-12 dígitos")
        return v

    @field_validator("telefono")
    def telefono_cr(cls, v):
        # normaliza: acepta 88888888 o +50688888888, permite guiones/espacios
        raw = re.sub(r"[\s\-]", "", v)
        digits = re.sub(r"\D", "", raw)
        # si viene con 506 prefijo, debe tener 11 dígitos (506 + 8)
        if digits.startswith("506"):
            if len(digits) != 11:
                raise ValueError("teléfono debe ser 88888888 o +50688888888")
        else:
            if len(digits) != 8:
                raise ValueError("teléfono 8 dígitos")
        return v

    @field_validator("mesa_numero", mode="before")
    def mesa_coerce(cls, v):
        if v == "" or v is None:
            return None
        try:
            return int(v)
        except:
            raise ValueError("mesa inválida")

# validación de monto según ubicación
    def validate_monto(self):
        expected = 10000 if self.ubicacion == "Mesas" else 5000
        if self.monto is not None and self.monto != expected:
            raise ValueError(f"monto debe ser {expected}")
        return expected
