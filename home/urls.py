from django.urls import path, include, re_path
from django.views.static import serve
from home import views
from django.conf import settings
from django.conf.urls.static import static
from .views import (
    add_to_cart,
    cart_count,
    shipping_page_view,
    update_delivery_option,
    move_to_order_placed,
    orders,
    create_razorpay_order,
    verify_razorpay_payment,
)

urlpatterns = [
    # ── Allauth (Google login, etc.) ──
    path('accounts/', include('allauth.urls')),

    # ── Loader (entry point) ──
    path('', views.loader, name='loader'),

    # ── Authentication ──
    path('login/', views.login_view, name='login'),
    path('signup/', views.signupUser, name='signup'),
    path('logout/', views.logoutUser, name='logout'),

    # ── Other pages ──
    path('homepage/', views.homepage, name='homepage'),
    path('product_detail/<str:product_id>/', views.product_detail, name='product_detail'),
    path('checkout/', views.checkout, name='checkout'),
    path('shipping/', views.shipping_page_view, name='shipping'),
    path('orders/', views.orders, name='orders'),
    path('contact/', views.contact, name='contact'),

    # ── Cart & order actions ──
    path('add_to_cart/<str:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart_count/', views.cart_count, name='cart_count'),
    path('update_delivery_option/<int:cart_item_id>/', views.update_delivery_option, name='update_delivery_option'),
    path('move_to_order_placed/', views.move_to_order_placed, name='move_to_order_placed'),

    # ── Online payment (Razorpay) ──
    path('create_razorpay_order/', create_razorpay_order, name='create_razorpay_order'),
    path('verify_razorpay_payment/', verify_razorpay_payment, name='verify_razorpay_payment'),
    path('pincode_lookup/<str:pin>/', views.pincode_lookup, name='pincode_lookup'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Serve media files in production too (static() above only works when DEBUG=True).
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]