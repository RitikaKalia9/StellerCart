import hashlib
import hmac
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import razorpay
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Avg, Q, Sum
from django.db.models.functions import Lower, Trim
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
import re
from home.forms import ACCEPTED, norm
from .models import Pincode
from home.models import Contact
from .forms import CustomerForm
from .models import (
    STATE_CHOICES,
    Cart,
    Customer,
    DeliveryOption,
    OrderPlaced,
    Product,
    Review,
)

TAX_RATE = Decimal('0.10')
CENT = Decimal('0.01')
MAX_QTY = 10


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def get_rating_image(rating_stars):
    """Map a rating to its star image, snapping to the nearest half star."""
    rating_images = {
        0: 'rating-0.png',
        0.5: 'rating-0.5.png',
        1: 'rating-1.0.png',
        1.5: 'rating-1.5.png',
        2: 'rating-2.0.png',
        2.5: 'rating-2.5.png',
        3: 'rating-3.0.png',
        3.5: 'rating-3.5.png',   # was missing -> 3.5-star products showed 0 stars
        4: 'rating-4.0.png',
        4.5: 'rating-4.5.png',
        5: 'rating-5.0.png',
    }
    if rating_stars is None:
        return rating_images[0]
    snapped = round(float(rating_stars) * 2) / 2
    snapped = max(0, min(5, snapped))
    return rating_images.get(snapped, rating_images[0])


def _cart_count_for(user):
    return Cart.objects.filter(user=user).aggregate(total=Sum('quantity'))['total'] or 0


def _line_breakdown(cart_item):
    """Single source of truth for pricing one cart line.
    Returns (subtotal, shipping, tax, total), all quantized to 2 dp so the
    amount shown, the amount charged and the amount stored always match."""
    subtotal = cart_item.product.price_rupees * cart_item.quantity
    shipping = (
        cart_item.delivery_option.price_rupees
        if cart_item.delivery_option else Decimal('0')
    )
    tax = (subtotal * TAX_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
    total = subtotal + shipping + tax
    return subtotal, shipping, tax, total


def _cart_total_paise(user):
    """Recompute the cart total server-side (never trust a client-supplied
    amount) and return it in paise, the unit Razorpay expects for INR."""
    cart_items = Cart.objects.filter(user=user).select_related('product', 'delivery_option')
    total = sum((_line_breakdown(ci)[3] for ci in cart_items), Decimal('0'))
    return int((total * 100).to_integral_value(rounding=ROUND_HALF_UP))


@transaction.atomic
def place_orders_from_cart(user):
    """Move every cart item of `user` into an OrderPlaced record (snapshotting
    the shipping address) and empty the cart.

    Atomic: if anything fails midway, no orders are created and no cart rows
    are deleted. `total_cost` now includes tax + shipping, i.e. exactly what
    the customer paid for that line.
    """
    customer = Customer.objects.filter(user=user).order_by('-id').first()
    cart_items = list(
        Cart.objects.select_for_update(of=('self',))
        .filter(user=user)
        .select_related('product', 'delivery_option')
    )

    created_orders = []
    for cart_item in cart_items:
        _, _, _, line_total = _line_breakdown(cart_item)
        order = OrderPlaced.objects.create(
            user=user,
            product=cart_item.product,
            quantity=cart_item.quantity,
            total_cost=line_total,
            shipping_name=customer.name if customer else '',
            shipping_phone=customer.phone if customer else '',
            shipping_address=customer.address if customer else '',
            shipping_city=customer.city if customer else '',
            shipping_zipcode=customer.zipcode if customer else '',
            shipping_state=customer.state if customer else '',
        )
        created_orders.append(order)
        cart_item.delete()

    return created_orders


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def loader(request):
    """Dedicated loader page - entry point with optional next parameter"""
    next_url = request.GET.get('next', 'login')
    return render(request, 'loader.html', {'next_url': next_url})


@login_required
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.rating_image = get_rating_image(product.rating_stars)

    if request.method == 'POST' and 'submit_review' in request.POST:
        try:
            rating = int(request.POST.get('rating', 0))
        except (TypeError, ValueError):
            rating = 0
        comment = request.POST.get('comment', '').strip()
        if 1 <= rating <= 5:
            Review.objects.create(
                product=product,
                user=request.user,
                rating=rating,
                comment=comment,
            )
            messages.success(request, "Your review was submitted!")
            return redirect('product_detail', product_id=product.id)
        else:
            messages.error(request, "Please select a valid rating.")

    reviews = product.reviews.all()
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    avg_rating = round(avg_rating, 1)
    avg_rating_image = get_rating_image(avg_rating)

    related_products = list(
        Product.objects.filter(category=product.category).exclude(id=product.id)[:4]
    ) if product.category else []

    if len(related_products) < 4:
        existing_ids = [p.id for p in related_products] + [product.id]
        extra = Product.objects.exclude(id__in=existing_ids).order_by('?')[:4 - len(related_products)]
        related_products = related_products + list(extra)

    context = {
        'product': product,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'avg_rating_image': avg_rating_image,
        'review_count': reviews.count(),
        'related_products': related_products,
        'fuel_units': 0,
        'cart_count': _cart_count_for(request.user),
    }
    return render(request, 'product_detail.html', context)


@login_required
def update_delivery_option(request, cart_item_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)

    cart_item = Cart.objects.filter(id=cart_item_id, user=request.user).first()
    if cart_item is None:
        return JsonResponse({'error': 'Cart item does not exist'}, status=404)

    raw_id = request.POST.get('delivery_option')
    if not raw_id or not str(raw_id).isdigit():
        return JsonResponse({'error': 'Invalid delivery option'}, status=400)

    option = DeliveryOption.objects.filter(id=int(raw_id)).first()
    if option is None:
        return JsonResponse({'error': 'Invalid delivery option'}, status=400)

    cart_item.delivery_option = option
    cart_item.save()
    return redirect('checkout')


def cart_count(request):
    count = _cart_count_for(request.user) if request.user.is_authenticated else 0
    return JsonResponse({'cart_count': count})


@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    try:
        selected_quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        selected_quantity = 1
    selected_quantity = max(1, min(selected_quantity, MAX_QTY))

    cart, created = Cart.objects.get_or_create(user=request.user, product=product)
    if created:
        cart.quantity = selected_quantity
    else:
        cart.quantity = min(cart.quantity + selected_quantity, MAX_QTY)
    cart.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'message': 'added', 'quantity': cart.quantity})
    return redirect('homepage')


def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(reverse('loader') + '?next=homepage')
        messages.error(request, "Invalid username or password.")
    return render(request, 'login.html')


@login_required
def homepage(request):
    just_logged_in = request.session.pop('just_logged_in', False)
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()

    products = Product.objects.all()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(keywords__icontains=query))
    elif category:
        # Trim + lower on both sides so stray whitespace/case in the DB
        # doesn't make a category look empty.
        products = products.annotate(
            _clean_category=Trim(Lower('category'))
        ).filter(_clean_category=category.strip().lower())
    products = list(products.order_by('-id'))

    for product in products:
        product.rating_image = get_rating_image(product.rating_stars)

    categories = ['electronics', 'fashion', 'home', 'sports']
    category_products = {}
    for cat in categories:
        cat_qs = list(
            Product.objects.annotate(_clean_category=Trim(Lower('category')))
            .filter(_clean_category=cat)
            .order_by('-id')[:4]
        )
        for product in cat_qs:
            product.rating_image = get_rating_image(product.rating_stars)
        category_products[cat] = cat_qs

    featured = list(Product.objects.filter(rating_stars__gte=4).order_by('-rating_stars')[:8])
    for product in featured:
        product.rating_image = get_rating_image(product.rating_stars)

    return render(request, 'homepage.html', {
        'products': products,
        'query': query,
        'category': category,
        'categories': categories,
        'category_products': category_products,
        'featured': featured,
        'just_logged_in': just_logged_in,
        'cart_count': _cart_count_for(request.user),
        'fuel_units': 0,
    })


def logoutUser(request):
    logout(request)
    return redirect('login')


def signupUser(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        fname = request.POST.get('fname', '').strip()
        lname = request.POST.get('lname', '').strip()
        email = request.POST.get('email', '').strip()
        pass1 = request.POST.get('pass1', '')
        pass2 = request.POST.get('pass2', '')

        if not username or not email:
            messages.error(request, "Username and email are required")
        elif len(username) > 30:
            messages.error(request, "Username must be under 30 characters")
        elif not username.isalnum():
            messages.error(request, "Username should only contain letters and numbers")
        elif pass1 != pass2:
            messages.error(request, "Passwords do not match.")
        elif len(pass1) < 8:
            messages.error(request, "Password must be at least 8 characters")
        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, 'Username already taken')
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Email already taken')
        else:
            myuser = User.objects.create_user(username, email, pass1)
            myuser.first_name = fname
            myuser.last_name = lname
            myuser.save()
            messages.success(request, "Congratulations! You've successfully created an account with StellerCart! Please proceed to log in to start exploring our platform.")
            return redirect('login')
        return redirect('signup')
    return render(request, 'signup.html')


@login_required
def checkout(request):
    if request.method == 'POST':
        if 'update_quantity' in request.POST:
            cart_item_id = request.POST.get('cart_item_id')
            try:
                new_quantity = int(request.POST.get('quantity'))
            except (TypeError, ValueError):
                messages.error(request, "Invalid quantity.")
                return redirect('checkout')
            new_quantity = max(1, min(new_quantity, MAX_QTY))
            cart_item = Cart.objects.filter(id=cart_item_id, user=request.user).first()
            if cart_item:
                cart_item.quantity = new_quantity
                cart_item.save()
        elif 'delete_item' in request.POST:
            cart_item_id = request.POST.get('cart_item_id')
            Cart.objects.filter(id=cart_item_id, user=request.user).delete()
        return redirect('checkout')

    cart_items = list(
        Cart.objects.filter(user=request.user).select_related('product', 'delivery_option')
    )
    total_items = sum(ci.quantity for ci in cart_items)

    total_price = Decimal('0')
    shipping = Decimal('0')
    tax = Decimal('0')
    total = Decimal('0')
    today = datetime.today()
    free_shipping_option = DeliveryOption.objects.filter(price_rupees=0).first()

    for cart_item in cart_items:
        if cart_item.delivery_option is None and free_shipping_option:
            cart_item.delivery_option = free_shipping_option
            cart_item.save()

        if cart_item.delivery_option:
            cart_item.delivery_date = today + timedelta(days=cart_item.delivery_option.delivery_days)
        else:
            cart_item.delivery_date = None

        line_sub, line_ship, line_tax, line_total = _line_breakdown(cart_item)
        total_price += line_sub
        shipping += line_ship
        tax += line_tax
        total += line_total

    delivery_options = DeliveryOption.objects.all()
    for option in delivery_options:
        option.delivery_date = today + timedelta(days=option.delivery_days)

    context = {
        'cart_items': cart_items,
        'total_items': total_items,
        'total_price': total_price,
        'shipping': shipping,
        'tax': tax,
        'total': total,
        'delivery_options': delivery_options,
    }
    return render(request, 'checkout.html', context)


@login_required
def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        desc = request.POST.get('desc')
        Contact.objects.create(
            user=request.user, name=name, email=email,
            phone=phone, desc=desc, date=datetime.today(),
        )
        messages.success(request, "Thank you for contacting us!")
        return redirect('contact')

    customer = Customer.objects.filter(user=request.user).order_by('-id').first()
    prefill_name = (
        customer.name if customer and customer.name else request.user.get_full_name()
    ) or request.user.username

    context = {
        'prefill_name': prefill_name,
        'prefill_email': request.user.email,
        'prefill_phone': customer.phone if customer else '',
        'cart_count': _cart_count_for(request.user),
        'fuel_units': 0,
    }
    return render(request, 'contact.html', context)


@login_required
def shipping_page_view(request):
    customer = Customer.objects.filter(user=request.user).order_by('-id').first()

    if request.method == 'POST':
        form = CustomerForm(request.POST, user=request.user)
        if form.is_valid():
            # Reuse the latest row explicitly (update_or_create would raise
            # MultipleObjectsReturned if old duplicates exist).
            obj = customer or Customer(user=request.user)
            for field, value in form.cleaned_data.items():
                setattr(obj, field, value)
            obj.save()
            messages.success(request, 'Shipping details saved. You can now place your order.')
            return redirect('shipping')

        for field, errs in form.errors.items():
            label = '' if field == '__all__' else f'{field.title()}: '
            for err in errs:
                messages.error(request, f'{label}{err}')
        # Re-render with what the user typed instead of wiping the form.
        customer = Customer(user=request.user, **{
            f: request.POST.get(f, '') for f in CustomerForm.Meta.fields
        })

    return render(request, 'shipping.html', {
        'STATE_CHOICES': STATE_CHOICES,
        'customer': customer,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    })


# --------------------------------------------------------------------------
# Orders / payments
# --------------------------------------------------------------------------

@login_required
@require_POST
def move_to_order_placed(request):
    """Cash-on-delivery order placement. No payment gateway involved."""
    if not Cart.objects.filter(user=request.user).exists():
        return JsonResponse({'error': 'Your cart is empty'}, status=400)

    if not Customer.objects.filter(user=request.user).exists():
        return JsonResponse({'error': 'Please save your shipping details first'}, status=400)

    place_orders_from_cart(request.user)
    messages.success(request, "Thank you for placing your order with steller cart!")
    return JsonResponse({'message': 'Order placed successfully', 'redirect_url': reverse('shipping')})


@login_required
@require_POST
def create_razorpay_order(request):
    """Step 1 of online payment: create a Razorpay order for the user's
    current cart total and bind it to this session."""
    if not Cart.objects.filter(user=request.user).exists():
        return JsonResponse({'error': 'Your cart is empty'}, status=400)

    if not Customer.objects.filter(user=request.user).exists():
        return JsonResponse({'error': 'Please save your shipping details first'}, status=400)

    amount_paise = _cart_total_paise(request.user)
    if amount_paise <= 0:
        return JsonResponse({'error': 'Invalid order amount'}, status=400)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    try:
        razorpay_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
        })
    except Exception as e:
        return JsonResponse({'error': f'Could not create payment order: {e}'}, status=502)

    # Bind this Razorpay order (and the amount it was created for) to the
    # session so verify can prove the payment matches the current cart.
    request.session['rzp_order'] = {'id': razorpay_order['id'], 'amount': amount_paise}

    return JsonResponse({
        'order_id': razorpay_order['id'],
        'amount': amount_paise,
        'currency': 'INR',
        'key_id': settings.RAZORPAY_KEY_ID,
    })


@login_required
@require_POST
def verify_razorpay_payment(request):
    """Step 2 of online payment: verify the signature, confirm the paid order
    belongs to this session and still matches the cart total, and only then
    create the orders / clear the cart."""
    razorpay_payment_id = request.POST.get('razorpay_payment_id')
    razorpay_order_id = request.POST.get('razorpay_order_id')
    razorpay_signature = request.POST.get('razorpay_signature')

    if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
        return JsonResponse({'error': 'Missing payment fields'}, status=400)

    generated_signature = hmac.new(
        key=settings.RAZORPAY_KEY_SECRET.encode(),
        msg=f'{razorpay_order_id}|{razorpay_payment_id}'.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(generated_signature, razorpay_signature):
        return JsonResponse({'error': 'Payment verification failed'}, status=400)

    if not Cart.objects.filter(user=request.user).exists():
        # Nothing to place (e.g. duplicate handler call) - no order is created.
        return JsonResponse({'message': 'Order already placed', 'redirect_url': reverse('shipping')})

    # Replay / cart-tampering protection.
    saved = request.session.get('rzp_order')
    if (
        not saved
        or saved.get('id') != razorpay_order_id
        or saved.get('amount') != _cart_total_paise(request.user)
    ):
        return JsonResponse({'error': 'Cart changed after payment started'}, status=400)

    place_orders_from_cart(request.user)
    request.session.pop('rzp_order', None)  # one-time use
    messages.success(request, "Payment successful! Thank you for your order with Steller Cart!")
    return JsonResponse({'message': 'Order placed successfully', 'redirect_url': reverse('shipping')})


@login_required
def orders(request):
    user_orders = OrderPlaced.objects.filter(user=request.user).select_related('product')
    grouped_orders = {}
    for order in user_orders:
        grouped_orders.setdefault(order.ordered_date, []).append(order)

    return render(request, 'orders.html', {
        'grouped_orders': grouped_orders,
        'cart_count': _cart_count_for(request.user),
        'fuel_units': 0,
    })

@login_required
def pincode_lookup(request, pin):
    if not re.fullmatch(r"\d{6}", pin):
        return JsonResponse({"error": "invalid"}, status=400)

    rows = list(Pincode.objects.filter(pincode=pin))
    if not rows:
        return JsonResponse({"error": "not_found"}, status=404)

    state_name = norm(rows[0].state)
    state_code = next(
        (code for code, names in ACCEPTED.items() if state_name in names), ""
    )
    return JsonResponse({
        "state_code": state_code,
        "city": rows[0].district.title(),
    })
