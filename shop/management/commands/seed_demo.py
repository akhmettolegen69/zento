import io
import random

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from shop.models import Category, Product, ProductImage, Store, Story, StorySlide

CATS = [('Women', '#B0305A'), ('Men', '#4C5BF5'), ('Kids', '#e07a1f'), ('Outerwear', '#2f5d62'),
        ('Sportswear', '#1f9d55'), ('Shoes', '#7b4b2a'), ('Accessories', '#6a4c93')]
# (name, username, city, bio, colour, verified)
STORES = [
    ('Urban Line', 'urbanline', 'Almaty', 'Streetwear & everyday basics.\nNew drops every Friday.', '#222831', True),
    ('Nomad Kids', 'nomadkids', 'Astana', 'Comfy clothes for little explorers.', '#e07a1f', False),
    ('Steppe Sport', 'steppesport', 'Shymkent', 'Gear for running, gym and outdoors.', '#1f9d55', True),
    ('Aru Boutique', 'aruboutique', 'Almaty', 'Dresses, scarves and accessories.', '#B0305A', False),
]
# (product name, category slug, store username, pinned)
ITEMS = [
    ('Linen shirt', 'men', 'urbanline', True), ('Puffer jacket', 'outerwear', 'urbanline', True),
    ('White sneakers', 'shoes', 'urbanline', False), ('Leather belt', 'accessories', 'urbanline', False),
    ('Cargo pants', 'men', 'urbanline', False), ('Oversized tee', 'men', 'urbanline', False),
    ('Kids hoodie', 'kids', 'nomadkids', True), ('Kids raincoat', 'outerwear', 'nomadkids', False),
    ('Kids sneakers', 'shoes', 'nomadkids', False), ('Kids beanie', 'accessories', 'nomadkids', False),
    ('Running leggings', 'sportswear', 'steppesport', True), ('Trail shoes', 'shoes', 'steppesport', False),
    ('Windbreaker', 'outerwear', 'steppesport', False), ('Gym shorts', 'sportswear', 'steppesport', False),
    ('Summer dress', 'women', 'aruboutique', False), ('Wool scarf', 'accessories', 'aruboutique', False),
    ('Silk blouse', 'women', 'aruboutique', False), ('Midi skirt', 'women', 'aruboutique', False),
]


def img(label, color, size=(1080, 1350)):
    im = Image.new('RGB', size, color)
    d = ImageDraw.Draw(im)
    d.ellipse((size[0] * .25, size[1] * .25, size[0] * .75, size[1] * .75), fill=(255, 255, 255))
    d.text((size[0] * .38, size[1] * .49), label, fill=color)
    buf = io.BytesIO()
    im.save(buf, 'JPEG')
    return ContentFile(buf.getvalue(), name=label.replace(' ', '_') + '.jpg')


class Command(BaseCommand):
    help = 'Create demo stores, categories, products and stories with placeholder images'

    def handle(self, *args, **opts):
        random.seed(1)
        cats = {}
        for i, (name, color) in enumerate(CATS):
            c, _ = Category.objects.get_or_create(slug=name.lower(), defaults={'name': name, 'color': color, 'position': i})
            if not c.image:
                c.image.save(f'{name}.jpg', img(name, color, (300, 300)))
            cats[c.slug] = (c, color)

        stores = {}
        for i, (name, slug, city, bio, color, verified) in enumerate(STORES):
            s, created = Store.objects.get_or_create(slug=slug, defaults={
                'name': name, 'city': city, 'bio': bio, 'verified': verified, 'position': i})
            if created:
                s.logo.save(f'{slug}.jpg', img(name[:1], color, (300, 300)))
            stores[slug] = (s, color)

        for i, (name, cat, slug, pinned) in enumerate(ITEMS):
            store, color = stores[slug]
            if store.products.filter(name=name).exists():
                continue
            c, ccolor = cats[cat]
            p = Product.objects.create(
                store=store, name=name, category=c, image=img(name, ccolor), price_kzt=random.randrange(3, 60) * 1000,
                description=f'{name} — quality item from @{slug}.', pinned=pinned,
                available=i % 7 != 6, badge=['new', 'popular', '', 'sale', ''][i % 5],
                delivery_days_min=5 + i % 6, delivery_days_max=10 + i % 6 * 2)
            if pinned:  # pinned posts get a carousel
                for k in (2, 3):
                    ProductImage.objects.create(product=p, position=k, image=img(f'{name} {k}', color))

        if not Story.objects.exists():
            for slug, (store, color) in stores.items():
                p = store.products.filter(available=True).first()
                s = Story.objects.create(title=store.name[:14], store=store, product=p,
                                         cover=img(store.name[:1], color, (300, 300)))
                StorySlide.objects.create(story=s, image=img(store.name, color, (720, 1280)), caption=store.name)
                if p:
                    StorySlide.objects.create(story=s, image=img(p.name, '#222', (720, 1280)), caption=p.name)
        self.stdout.write('Demo data created.')
