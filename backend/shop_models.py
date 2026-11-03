from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CleanModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class Category(CleanModel):
    name: str = Field(min_length=1, max_length=100)
    active: bool = True


class CategoryEdit(Category):
    version: int = Field(gt=0)


class Product(CleanModel):
    category_id: int = Field(gt=0)
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=5000)
    price_paise: int = Field(strict=True, ge=1, le=100000000)
    low_stock_threshold: int = Field(default=5, ge=0, le=1000000)
    active: bool = False


class ProductCreate(Product):
    initial_stock: int = Field(default=0, ge=0, le=1000000)


class ProductEdit(Product):
    version: int = Field(gt=0)


class StockAdjustment(CleanModel):
    version: int = Field(gt=0)
    delta: int = Field(strict=True, ge=-1000000, le=1000000)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator('delta')
    @classmethod
    def nonzero(cls, v):
        if not v:
            raise ValueError('Stock adjustment must be nonzero')
        return v


class CartItem(CleanModel):
    version: int = Field(gt=0)
    quantity: int = Field(strict=True, ge=0, le=99)


class Checkout(CleanModel):
    version: int = Field(gt=0)
    checkout_key: UUID
    expected_total_paise: int = Field(strict=True, gt=0)
    customer_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=30)
    address: str = Field(min_length=5, max_length=500)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(pattern=r'^\d{6}$')


class OrderDecision(CleanModel):
    version: int = Field(gt=0)
    action: Literal['confirm', 'ship', 'deliver', 'cancel']
    note: str = Field(default='', max_length=1000)
    tracking_reference: str = Field(default='', max_length=200)
