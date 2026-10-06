from django.contrib import admin
from home.models import Contact
from home.models import Customer
from home.models import Product
from home.models import Cart
from home.models import DeliveryOption
from home.models import OrderPlaced
from home.models import Review

# Register your models here.
admin.site.register(Contact)

admin.site.register(Customer)

admin.site.register(Product)

admin.site.register(Cart)

admin.site.register(DeliveryOption)

admin.site.register(OrderPlaced)

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'user__username', 'comment')