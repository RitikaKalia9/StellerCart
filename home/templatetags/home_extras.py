from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key. Usage: {{ dict|get_item:key }}"""
    return dictionary.get(key)

@register.filter
def cart_quantity_total(cart_items):
    """Sum the quantity field across a list of Cart items."""
    if not cart_items:
        return 0
    return sum(item.quantity for item in cart_items)