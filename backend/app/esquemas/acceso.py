"""Acceso: inicio de sesión, perfil, proveedores, usuarios, roles y empresa.
"""
from typing import Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class DesafioIn(BaseModel):
    desafio: str = Field(max_length=100)


class VerificarIn(DesafioIn):
    codigo: str = Field(max_length=10)


class PasswordIn(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


class ProveedorIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=200)
    activo: bool = True


class ProveedorPatch(BaseModel):
    nombre: str | None = None
    activo: bool | None = None


class FotoIn(BaseModel):
    foto: str | None = Field(default=None, max_length=400_000)  # data URL de una imagen reducida; vacío la quita


class PerfilIn(BaseModel):
    nombre: str | None = Field(default=None, max_length=200)
    idioma: str | None = None
    idioma_documentos: str | None = None  # PDF y Excel; vacío = el de la pantalla
    formato_fecha: str | None = None
    formato_hora: str | None = None
    formato_numero: str | None = None
    tema: str | None = None
    filas: int | None = None
    inicio: str | None = None


class RolIn(BaseModel):
    nombre: str = Field(max_length=80)
    descripcion: str | None = Field(default=None, max_length=300)
    permisos: list[str] = []
    datos_ocultos: list[str] = []
    activo: bool = True


class RolPatch(BaseModel):
    nombre: str | None = Field(default=None, max_length=80)
    descripcion: str | None = Field(default=None, max_length=300)
    permisos: list[str] | None = None
    datos_ocultos: list[str] | None = None
    activo: bool | None = None


class UsuarioIn(BaseModel):
    email: str
    nombre: str
    rol: Literal["admin", "interno", "proveedor"] | None = None
    rol_id: int | None = None
    proveedor_id: int | None = None
    password: str | None = Field(default=None, max_length=200)  # vacío: se genera una temporal
    telefono: str | None = None
    dos_pasos: bool = True
    cargo: str | None = Field(default=None, max_length=120)
    area: str | None = Field(default=None, max_length=120)
    empresa: str | None = Field(default=None, max_length=200)


class UsuarioPatch(BaseModel):
    nombre: str | None = None
    rol: Literal["admin", "interno", "proveedor"] | None = None
    rol_id: int | None = None
    proveedor_id: int | None = None
    password: str | None = Field(default=None, max_length=200)
    generar_clave: bool | None = None  # restablecer con una contraseña temporal generada
    activo: bool | None = None
    telefono: str | None = None
    dos_pasos: bool | None = None
    email: str | None = Field(default=None, max_length=200)
    cargo: str | None = Field(default=None, max_length=120)
    area: str | None = Field(default=None, max_length=120)
    empresa: str | None = Field(default=None, max_length=200)
