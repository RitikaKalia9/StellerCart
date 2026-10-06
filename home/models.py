from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator

# Create your models here.

# Contact model
class Contact(models.Model):
  user = models.ForeignKey(User, on_delete=models.CASCADE,default=None, null=True)
  name = models.CharField(max_length=122)
  email = models.CharField(max_length=122)
  phone = models.CharField(max_length=12)
  desc = models.TextField()
  date = models.DateField()

  def __str__(self):
      return self.name

STATE_CHOICES = (
   ("AN","Andaman and Nicobar Islands"),
   ("AP","Andhra Pradesh"),
   ("AR","Arunachal Pradesh"),
   ("AS","Assam"),
   ("BR","Bihar"),
   ("CG","Chhattisgarh"),
   ("CH","Chandigarh"),
   ("DN","Dadra and Nagar Haveli"),
   ("DD","Daman and Diu"),
   ("DL","Delhi"),
   ("GA","Goa"),
   ("GJ","Gujarat"),
   ("HR","Haryana"),
   ("HP","Himachal Pradesh"),
   ("JK","Jammu and Kashmir"),
   ("JH","Jharkhand"),
   ("KA","Karnataka"),
   ("KL","Kerala"),
   ("LA","Ladakh"),
   ("LD","Lakshadweep"),
   ("MP","Madhya Pradesh"),
   ("MH","Maharashtra"),
   ("MN","Manipur"),
   ("ML","Meghalaya"),
   ("MZ","Mizoram"),
   ("NL","Nagaland"),
   ("OD","Odisha"),
   ("PB","Punjab"),
   ("PY","Pondicherry"),
   ("RJ","Rajasthan"),
   ("SK","Sikkim"),
   ("TN","Tamil Nadu"),
   ("TS","Telangana"),
   ("TR","Tripura"),
   ("UP","Uttar Pradesh"),
   ("UK","Uttarakhand"),
   ("WB","West Bengal")
)


# Customer model
class Customer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    zipcode = models.CharField(max_length=10, null=True)
    state = models.CharField(max_length=50, choices=STATE_CHOICES)

    def __str__(self):
        return self.name

#Product model
class Product(models.Model):
    id = models.CharField(primary_key=True, max_length=36)
    image = models.ImageField(upload_to='products/')
    name = models.CharField(max_length=255)
    rating_stars = models.FloatField(null=True, blank=True)
    rating_count = models.IntegerField(null=True, blank=True)
    price_rupees = models.DecimalField(max_digits=10, decimal_places=2)
    keywords = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    # (added: product_detail.html renders {{ product.description }}, but
    # this field never existed on the model, so it always silently fell
    # back to "No description available." Adding it here so the field is
    # real and can actually be filled in via admin/shell.)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])  # 1-5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.product.name} - {self.rating}⭐"

# DeliveryOption model
class DeliveryOption(models.Model):
    # Remove the 'id' field declaration, Django will automatically create an 'id' field as the primary key
    delivery_days = models.PositiveIntegerField()
    price_rupees = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Delivery Option {self.pk}: {self.delivery_days} days, ₹{self.price_rupees}"


# Cart model
class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    delivery_option = models.ForeignKey(DeliveryOption, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"User: {self.user.username}, Product: {self.product.name}, Quantity: {self.quantity}, Delivery Option: {self.delivery_option}"

# orderPlaced model
class OrderPlaced(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    ordered_date = models.DateField(auto_now_add=True)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)

    # Snapshot of shipping details at time of order — immune to later
    # address edits, unlike a ForeignKey to a mutable Customer row.
    shipping_name = models.CharField(max_length=100, blank=True)
    shipping_phone = models.CharField(max_length=20, blank=True)
    shipping_address = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_zipcode = models.CharField(max_length=10, blank=True, null=True)
    shipping_state = models.CharField(max_length=50, choices=STATE_CHOICES, blank=True)

    def __str__(self):
        return f"OrderPlaced - User: {self.user.username}, Product: {self.product.name}, Quantity: {self.quantity}, Ordered Date: {self.ordered_date}"


# Pincode model: local copy of the India Post pincode directory, used to
# validate PIN / city / state without calling an external API.
class Pincode(models.Model):
    pincode = models.CharField(max_length=6, db_index=True)
    office = models.CharField(max_length=150)
    district = models.CharField(max_length=100, db_index=True)
    division = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100)  # stored normalized (lowercase)

    def __str__(self):
        return f"{self.pincode} {self.office}"