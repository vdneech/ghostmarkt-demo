import pytest
import math
from src.orders.utils import calculate_dimensions
from src.shared.schemas import Dimensions

class MockProduct:
    def __init__(self, length, width, height):
        self.length = length
        self.width = width
        self.height = height

    @property
    def volume(self):
        return self.length * self.width * self.height

class MockOrderItem:
    def __init__(self, product, quantity):
        self.product = product
        self.quantity = quantity

def test_dimensions_small_items_fit_box_m():
    item1 = MockOrderItem(MockProduct(10, 10, 10), 1)
    item2 = MockOrderItem(MockProduct(5, 5, 5), 2)
    
    dims = calculate_dimensions([item1, item2])
    
    assert dims.length == 33
    assert dims.width == 25
    assert dims.height == 15

def test_dimensions_single_large_item():
    item = MockOrderItem(MockProduct(50, 10, 10), 1)
    
    dims = calculate_dimensions([item])
    
    assert dims.length == 50
    assert dims.width == 25
    assert dims.height == 15

def test_dimensions_large_volume_exceeds_box_m():
    item = MockOrderItem(MockProduct(20, 20, 20), 5) 
    
    dims = calculate_dimensions([item])
    
    assert dims.length >= 33
    assert dims.width >= 25
    assert dims.height >= 15
    
    expected_vol = 20 * 20 * 20 * 5 * 1.25
    assert dims.length * dims.width * dims.height >= expected_vol

def test_dimensions_long_and_large_volume():
    item1 = MockOrderItem(MockProduct(40, 10, 10), 1)
    item2 = MockOrderItem(MockProduct(20, 20, 20), 10)
    
    dims = calculate_dimensions([item1, item2])
    
    assert dims.length >= 40
    assert dims.width >= 25
    assert dims.height >= 15

def test_dimensions_empty_order():
    dims = calculate_dimensions([])
    
    assert dims.length == 33
    assert dims.width == 25
    assert dims.height == 15
