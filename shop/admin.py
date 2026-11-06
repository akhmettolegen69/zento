from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Follow, Order, OrderItem, Product, ProductImage, Profile, SiteSettings, Store, Story, StorySlide

admin.site.site_header = 'Zento admin'


def thumb(obj):
    f = getattr(obj, 'image', None) or getattr(obj, 'cover', None) or getattr(obj, 'logo', None)
    return format_html('<img src="{}" style="height:48px;border-radius:8px">', f.url) if f else '—'


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'position')
    list_editable = ('position',)
    prepopulated_fields = {'slug': ('name',)}


class StoreProductInline(admin.TabularInline):
    model = Product
    fields = ('name', 'price_kzt', 'available', 'pinned')
    extra = 0
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False  # products need an image: add them from the Products page


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = (thumb, 'name', 'slug', 'city', 'verified', 'active', 'position', 'product_count')
    list_editable = ('verified', 'active', 'position')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug')
    inlines = [StoreProductInline]

    @admin.display(description='Products')
    def product_count(self, obj):
        return obj.products.count()


class PhotoInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    verbose_name_plural = 'Extra photos (carousel)'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (thumb, 'name', 'store', 'category', 'price_kzt', 'price_cny_display', 'available',
                    'pinned', 'delivery_days_min', 'delivery_days_max', 'badge')
    list_editable = ('price_kzt', 'available', 'pinned', 'badge')
    list_filter = ('store', 'pinned', 'available', 'category')
    list_select_related = ('store', 'category')
    search_fields = ('name', 'store__name')
    inlines = [PhotoInline]

    @admin.display(description='Price (CNY)')
    def price_cny_display(self, obj):
        return f'¥{obj.price_cny}'


class SlideInline(admin.TabularInline):
    model = StorySlide
    extra = 1


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = (thumb, 'title', 'store', 'product', 'active', 'expires_at', 'position')
    list_editable = ('active', 'position')
    inlines = [SlideInline]


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('phone', 'user')
    search_fields = ('phone', 'user__first_name', 'user__last_name')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'name', 'price_kzt', 'quantity')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'status', 'total_kzt', 'total_cny', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('total_kzt', 'total_cny', 'rate', 'payment_ref', 'created_at')
    inlines = [OrderItemInline]


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'created_at')
    list_filter = ('store',)
