"""
Development demo data seeder command for Stage C3 Public Product Catalogue testing.

Safety Rules:
- Development environment ONLY (checks settings.DEBUG is True).
- Targets strictly two exact demo merchants ('demo-aura-silks' and 'demo-urban-ceramics').
- Never modifies or deletes unrelated merchants or stores (e.g. Krishna Garments is 100% untouched).
- Idempotent: checks for existence before creating; supports --refresh and --cleanup.
- Uses database transactions for atomic execution.
"""

import io
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.models import Merchant, MerchantMembership
from apps.products.choices import AvailabilityMode, PriceDisplayMode, ProductStatus
from apps.products.models import Category, Product, ProductCategory, ProductImage
from apps.stores.choices import StoreStatus
from apps.stores.models import Store

User = get_user_model()

# Exact, immutable demo identity constants
EXACT_DEMO_STORE_SLUGS = (
    "demo-aura-silks",
    "demo-urban-ceramics",
)

EXACT_DEMO_MERCHANT_EMAILS = (
    "demo-aura-silks@example.com",
    "demo-urban-ceramics@example.com",
)

EXACT_DEMO_USER_EMAILS = (
    "demo-aura-owner@example.com",
    "demo-urban-owner@example.com",
)

EXACT_DEMO_SKU_PREFIXES = (
    "AURA-",
    "URB-",
)

SENTINEL_PRICE = Decimal("133742.00")
SENTINEL_MRP = Decimal("199999.00")


def generate_synthetic_placeholder(
    title: str,
    subtitle: str,
    bg_color: tuple[int, int, int],
    filename: str,
) -> ContentFile:
    """
    Generates an explicit, lightweight 3:4 portrait graphic placeholder card (600x800).
    Explicitly watermarked as a synthetic demo placeholder, not realistic photography.
    """
    width, height = 600, 800
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Decorative inner borders
    draw.rectangle([(24, 24), (width - 24, height - 24)], outline=(255, 255, 255), width=2)
    draw.rectangle([(32, 32), (width - 32, height - 32)], outline=(255, 255, 255, 120), width=1)

    # Clean text labeling
    font = ImageFont.load_default()
    draw.text((48, 56), "MYCATALOGUE DEMO PLACEHOLDER", fill=(255, 255, 255), font=font)
    draw.text((48, 80), subtitle.upper(), fill=(230, 230, 230), font=font)

    # Centered title box
    words = title.split()
    lines = []
    current_line = []
    for w in words:
        current_line.append(w)
        if len(" ".join(current_line)) > 24:
            lines.append(" ".join(current_line[:-1]))
            current_line = [w]
    if current_line:
        lines.append(" ".join(current_line))

    y_start = height // 2 - (len(lines) * 16)
    for i, line in enumerate(lines[:3]):
        draw.text((48, y_start + (i * 24)), line, fill=(255, 255, 255), font=font)

    # Footer note
    draw.text(
        (48, height - 60),
        "Synthetic Visual Asset for C3 UI Testing",
        fill=(220, 220, 220),
        font=font,
    )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return ContentFile(buf.getvalue(), name=filename)


class Command(BaseCommand):
    help = "Seeds deterministic development demo data for C3 catalogue testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Cleans up existing demo records before re-seeding.",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Safely removes only the exact demo records and exits.",
        )

    def handle(self, *args, **options):
        # 1. Environment Safety Guard
        if not settings.DEBUG:
            raise CommandError(
                "SAFETY VIOLATION: seed_c3_demo_data can ONLY be run in development environments where DEBUG=True."
            )

        refresh = options.get("refresh", False)
        cleanup = options.get("cleanup", False)

        # 2. Cleanup mode or Refresh preparation
        if cleanup or refresh:
            self.stdout.write(
                self.style.WARNING("Performing targeted cleanup of known demo records...")
            )
            self._cleanup_demo_data()
            if cleanup:
                self.stdout.write(self.style.SUCCESS("Cleanup completed successfully. Exiting."))
                return

        # 3. Idempotency Check
        existing_demo_stores = Store.objects.filter(slug__in=EXACT_DEMO_STORE_SLUGS)
        if existing_demo_stores.exists() and not refresh:
            self.stdout.write(self.style.NOTICE("Demo stores already exist:"))
            for store in existing_demo_stores:
                product_count = Product.objects.filter(merchant=store.merchant).count()
                category_count = Category.objects.filter(merchant=store.merchant).count()
                self.stdout.write(
                    f" - {store.name} ({store.slug}): {category_count} categories, {product_count} products"
                )
            self.stdout.write(
                self.style.WARNING(
                    "\nTo reseed with a fresh dataset, run: python manage.py seed_c3_demo_data --refresh"
                )
            )
            return

        # 4. Atomic Seeding Execution
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding C3 Demo Data across 2 Merchants..."))
        with transaction.atomic():
            self._seed_store_alpha()
            self._seed_store_beta()

        self.stdout.write(self.style.SUCCESS("\nSuccessfully seeded C3 Demo Data!"))
        self._print_verification_summary()

    def _cleanup_demo_data(self):
        """Safely removes only records belonging to the exact two demo tenants."""
        with transaction.atomic():
            merchants = list(
                Merchant.objects.filter(
                    email__in=EXACT_DEMO_MERCHANT_EMAILS,
                    store__slug__in=EXACT_DEMO_STORE_SLUGS,
                )
            )
            users = list(User.objects.filter(email__in=EXACT_DEMO_USER_EMAILS))

            store_count = Store.objects.filter(merchant__in=merchants).count()
            product_count = Product.objects.filter(merchant__in=merchants).count()
            category_count = Category.objects.filter(merchant__in=merchants).count()
            image_count = ProductImage.objects.filter(product__merchant__in=merchants).count()
            membership_count = MerchantMembership.objects.filter(merchant__in=merchants).count()

            self.stdout.write(
                f"Found for deletion: {len(merchants)} merchants, {store_count} stores, "
                f"{category_count} categories, {product_count} products, {image_count} images, "
                f"{membership_count} memberships, {len(users)} users."
            )

            # Delete bottom-up respecting PROTECT foreign keys
            Store.objects.filter(merchant__in=merchants).delete()
            ProductImage.objects.filter(product__merchant__in=merchants).delete()
            ProductCategory.objects.filter(product__merchant__in=merchants).delete()
            Product.objects.filter(merchant__in=merchants).delete()
            Category.objects.filter(merchant__in=merchants).delete()
            MerchantMembership.objects.filter(merchant__in=merchants).delete()

            for m in merchants:
                m.delete()
            for u in users:
                u.delete()

            self.stdout.write(self.style.SUCCESS("Targeted cleanup finished."))

    def _seed_store_alpha(self):
        """Seeds Tenant A: Aura Silks & Handlooms (Textiles / Ethnic Fashion)."""
        user_alpha, _ = User.objects.get_or_create(
            email="demo-aura-owner@example.com",
            defaults={
                "first_name": "Ananya",
                "last_name": "Sharma",
                "is_active": True,
                "is_verified": True,
            },
        )
        user_alpha.set_password("DemoPassword123!")
        user_alpha.save()

        merchant_alpha, _ = Merchant.objects.get_or_create(
            email="demo-aura-silks@example.com",
            defaults={
                "name": "Aura Silks & Handlooms",
                "business_type": BusinessType.RETAIL,
                "contact_number": "+91 9876543210",
                "address": "42 Dashashwamedh Ghat Road",
                "city": "Varanasi",
                "state": "Uttar Pradesh",
                "pin_code": "221001",
                "status": MerchantStatus.ACTIVE,
                "description": "Artisanal handwoven Banarasi and Chanderi sarees direct from master weavers.",
            },
        )

        MerchantMembership.objects.get_or_create(
            user=user_alpha,
            merchant=merchant_alpha,
            defaults={
                "role": MembershipRole.OWNER,
                "status": MembershipStatus.ACTIVE,
            },
        )

        store_alpha, _ = Store.objects.get_or_create(
            merchant=merchant_alpha,
            defaults={
                "name": "Aura Silks & Handlooms",
                "slug": "demo-aura-silks",
                "tagline": "Pure Handcrafted Banarasi & Chanderi Silks",
                "description": "Authentic handloom sarees and festive kurtas directly from Varanasi.",
                "whatsapp_number": "+91 9876543210",
                "status": StoreStatus.PUBLISHED,
            },
        )

        # 6 Categories (including 1 empty category)
        categories_data = [
            ("Banarasi Silks", "banarasi-silks", 1),
            ("Chanderi Sarees", "chanderi-sarees", 2),
            ("Kanjeevaram Silk", "kanjeevaram-silk", 3),
            ("Dupattas & Stoles", "dupattas-stoles", 4),
            ("Festive Kurtas", "festive-kurtas", 5),
            ("Unstitched Fabrics", "unstitched-fabrics", 6),  # Intentionally 0 products
        ]
        cats = {}
        for name, slug, order in categories_data:
            cat, _ = Category.objects.get_or_create(
                merchant=merchant_alpha,
                slug=slug,
                defaults={"name": name, "display_order": order, "is_active": True},
            )
            cats[slug] = cat

        # 38 Products for Store Alpha
        palette = [
            (140, 40, 55),  # Crimson
            (35, 75, 115),  # Royal Blue
            (50, 110, 80),  # Emerald
            (160, 95, 30),  # Ochre Gold
            (105, 55, 120),  # Plum
            (65, 80, 95),  # Slate
        ]

        products_spec = [
            # 1. Banarasi Silks (10 items)
            (
                "Katan Silk Zari Saree",
                "banarasi-silks",
                Decimal("8999.00"),
                Decimal("12999.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-BAN-001",
                "primary",
            ),
            (
                "Kadwa Boota Banarasi Saree",
                "banarasi-silks",
                Decimal("14500.00"),
                Decimal("18500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-BAN-002",
                "primary",
            ),
            (
                "Jangla Floral Bridal Banarasi",
                "banarasi-silks",
                SENTINEL_PRICE,
                SENTINEL_MRP,
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.CONTACT_FOR_PRICE,
                "AURA-BAN-003",
                "primary",
            ),
            (
                "Tanchoi Weave Silk Saree",
                "banarasi-silks",
                Decimal("6999.00"),
                Decimal("9500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-BAN-004",
                "multi",
            ),
            (
                "Shikargah Banarasi Heritage",
                "banarasi-silks",
                SENTINEL_PRICE,
                SENTINEL_MRP,
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.CONTACT_FOR_PRICE,
                "AURA-BAN-005",
                "primary",
            ),
            (
                "Georgette Banarasi Saree",
                "banarasi-silks",
                Decimal("5499.00"),
                Decimal("7500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-BAN-006",
                "primary",
            ),
            (
                "Tissue Silk Banarasi Saree",
                "banarasi-silks",
                Decimal("11200.00"),
                Decimal("14000.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-BAN-007",
                "primary",
            ),
            (
                "Organza Zari Border Banarasi",
                "banarasi-silks",
                Decimal("4800.00"),
                Decimal("6200.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-BAN-008",
                "fallback_non_primary",
            ),
            (
                "Meenakari Banarasi Saree",
                "banarasi-silks",
                Decimal("16500.00"),
                Decimal("22000.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-BAN-009",
                "zero_image",
            ),
            (
                "Brocade Banarasi Traditional",
                "banarasi-silks",
                Decimal("7900.00"),
                Decimal("9900.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-BAN-010",
                "primary",
            ),
            # 2. Chanderi Sarees (8 items)
            (
                "Pure Chanderi Zari Border Saree",
                "chanderi-sarees",
                Decimal("3499.00"),
                Decimal("4500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-CHA-011",
                "primary",
            ),
            (
                "Chanderi Cotton Silk Pastel Saree",
                "chanderi-sarees",
                Decimal("2899.00"),
                Decimal("3800.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-CHA-012",
                "primary",
            ),
            (
                "Hand Block Printed Chanderi Saree",
                "chanderi-sarees",
                Decimal("3999.00"),
                Decimal("5200.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-CHA-013",
                "multi",
            ),
            (
                "Eknaliya Chanderi Masterpiece",
                "chanderi-sarees",
                SENTINEL_PRICE,
                SENTINEL_MRP,
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.CONTACT_FOR_PRICE,
                "AURA-CHA-014",
                "primary",
            ),
            (
                "Chanderi Tissue Saree in Gold",
                "chanderi-sarees",
                Decimal("6200.00"),
                Decimal("7800.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-CHA-015",
                "primary",
            ),
            (
                "Chanderi Floral Jaal Saree",
                "chanderi-sarees",
                Decimal("4200.00"),
                Decimal("5500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-CHA-016",
                "primary",
            ),
            (
                "Monochrome Chanderi Handloom",
                "chanderi-sarees",
                Decimal("3100.00"),
                Decimal("4200.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-CHA-017",
                "fallback_non_primary",
            ),
            (
                "Chanderi Pattu Silk Saree",
                "chanderi-sarees",
                Decimal("4950.00"),
                Decimal("6500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-CHA-018",
                "primary",
            ),
            # 3. Kanjeevaram Silk (8 items)
            (
                "Temple Border Kanjeevaram Silk",
                "kanjeevaram-silk",
                Decimal("18500.00"),
                Decimal("24000.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KAN-019",
                "primary",
            ),
            (
                "Korvai Weave Bridal Kanjeevaram",
                "kanjeevaram-silk",
                Decimal("28500.00"),
                Decimal("35000.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KAN-020",
                "multi",
            ),
            (
                "Muthu Kattam Kanjeevaram Check",
                "kanjeevaram-silk",
                Decimal("13999.00"),
                Decimal("17500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KAN-021",
                "primary",
            ),
            (
                "Royal Peacock Motif Kanjeevaram",
                "kanjeevaram-silk",
                SENTINEL_PRICE,
                SENTINEL_MRP,
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.CONTACT_FOR_PRICE,
                "AURA-KAN-022",
                "primary",
            ),
            (
                "Pastel Dual Tone Kanjeevaram",
                "kanjeevaram-silk",
                Decimal("15800.00"),
                Decimal("19500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KAN-023",
                "primary",
            ),
            (
                "Brocade Pallu Kanjeevaram Saree",
                "kanjeevaram-silk",
                Decimal("21000.00"),
                Decimal("27000.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KAN-024",
                "primary",
            ),
            (
                "Traditional Crimson Kanjeevaram",
                "kanjeevaram-silk",
                Decimal("19200.00"),
                Decimal("25000.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KAN-025",
                "zero_image",
            ),
            (
                "Lightweight Festive Kanjeevaram",
                "kanjeevaram-silk",
                Decimal("11500.00"),
                Decimal("14500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KAN-026",
                "primary",
            ),
            # 4. Dupattas & Stoles (6 items)
            (
                "Pure Banarasi Katan Silk Dupatta",
                "dupattas-stoles",
                Decimal("2499.00"),
                Decimal("3200.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-DUP-027",
                "primary",
            ),
            (
                "Chanderi Zari Border Dupatta",
                "dupattas-stoles",
                Decimal("1499.00"),
                Decimal("1999.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-DUP-028",
                "multi",
            ),
            (
                "Tussar Silk Hand Block Stole",
                "dupattas-stoles",
                Decimal("1899.00"),
                Decimal("2500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-DUP-029",
                "primary",
            ),
            (
                "Meenakari Jaal Silk Dupatta",
                "dupattas-stoles",
                Decimal("3200.00"),
                Decimal("4200.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-DUP-030",
                "primary",
            ),
            (
                "Organza Embroidered Dupatta",
                "dupattas-stoles",
                Decimal("1999.00"),
                Decimal("2600.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-DUP-031",
                "fallback_non_primary",
            ),
            (
                "Raw Silk Solid Stole with Tassels",
                "dupattas-stoles",
                Decimal("899.00"),
                Decimal("1200.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-DUP-032",
                "primary",
            ),
            # 5. Festive Kurtas (6 items)
            (
                "Handloom Raw Silk Kurta",
                "festive-kurtas",
                Decimal("3299.00"),
                Decimal("4299.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KUR-033",
                "primary",
            ),
            (
                "Banarasi Brocade Nehru Jacket & Kurta",
                "festive-kurtas",
                Decimal("5999.00"),
                Decimal("7999.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KUR-034",
                "multi",
            ),
            (
                "Chanderi Embroidered Festive Kurti",
                "festive-kurtas",
                Decimal("2799.00"),
                Decimal("3599.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KUR-035",
                "primary",
            ),
            (
                "Tussar Silk Pintuck Kurta",
                "festive-kurtas",
                Decimal("3499.00"),
                Decimal("4500.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KUR-036",
                "primary",
            ),
            (
                "Jacquard Woven Festive Kurta",
                "festive-kurtas",
                Decimal("2999.00"),
                Decimal("3899.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KUR-037",
                "zero_image",
            ),
            (
                "Linen Silk Minimalist Kurta",
                "festive-kurtas",
                Decimal("2199.00"),
                Decimal("2899.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "AURA-KUR-038",
                "primary",
            ),
        ]

        now = timezone.now()
        for idx, item in enumerate(products_spec):
            name, cat_slug, price, mrp, avail, price_mode, sku, img_mode = item
            is_avail = avail != AvailabilityMode.OUT_OF_STOCK
            slug = f"aura-{name.lower().replace(' ', '-').replace('&', 'and')[:40]}"

            product, _ = Product.objects.get_or_create(
                merchant=merchant_alpha,
                sku=sku,
                defaults={
                    "name": name,
                    "slug": slug,
                    "price": price,
                    "mrp": mrp,
                    "price_display_mode": price_mode,
                    "availability_mode": avail,
                    "is_available": is_avail,
                    "status": ProductStatus.PUBLISHED,
                    "description": f"Exquisite handcrafted {name} featuring premium natural yarns.",
                },
            )

            # Assign category through ProductCategory
            target_cat = cats[cat_slug]
            ProductCategory.objects.get_or_create(product=product, category=target_cat)

            # Assign staggered created_at timestamp for deterministic sort verification
            staggered_date = now - timedelta(days=idx + 1, hours=(idx * 2) % 24)
            Product.objects.filter(id=product.id).update(created_at=staggered_date)

            # Image handling
            color = palette[idx % len(palette)]
            if img_mode == "primary":
                f = generate_synthetic_placeholder(
                    name, target_cat.name, color, f"aura_{idx}_prim.jpg"
                )
                ProductImage.objects.create(
                    product=product, image=f, is_primary=True, display_order=1
                )
            elif img_mode == "multi":
                f1 = generate_synthetic_placeholder(
                    name, target_cat.name, color, f"aura_{idx}_m1.jpg"
                )
                ProductImage.objects.create(
                    product=product, image=f1, is_primary=True, display_order=1
                )
                f2 = generate_synthetic_placeholder(
                    f"{name} (Detail)", "Detail View", color, f"aura_{idx}_m2.jpg"
                )
                ProductImage.objects.create(
                    product=product, image=f2, is_primary=False, display_order=2
                )
            elif img_mode == "fallback_non_primary":
                f = generate_synthetic_placeholder(
                    name, "Gallery Fallback", color, f"aura_{idx}_nonprim.jpg"
                )
                ProductImage.objects.create(
                    product=product, image=f, is_primary=False, display_order=1
                )
            # zero_image mode creates 0 ProductImage instances to test neutral fallback placeholder

    def _seed_store_beta(self):
        """Seeds Tenant B: Urban Clay & Ceramics (Studio Pottery / Home Living)."""
        user_beta, _ = User.objects.get_or_create(
            email="demo-urban-owner@example.com",
            defaults={
                "first_name": "Vikram",
                "last_name": "Rathore",
                "is_active": True,
                "is_verified": True,
            },
        )
        user_beta.set_password("DemoPassword123!")
        user_beta.save()

        merchant_beta, _ = Merchant.objects.get_or_create(
            email="demo-urban-ceramics@example.com",
            defaults={
                "name": "Urban Clay & Ceramics",
                "business_type": BusinessType.RETAIL,
                "contact_number": "+91 9123456789",
                "address": "18 MI Road, C-Scheme",
                "city": "Jaipur",
                "state": "Rajasthan",
                "pin_code": "302001",
                "status": MerchantStatus.ACTIVE,
                "description": "Studio handcrafted stoneware, ceramic tableware, and minimalist planters.",
            },
        )

        MerchantMembership.objects.get_or_create(
            user=user_beta,
            merchant=merchant_beta,
            defaults={
                "role": MembershipRole.OWNER,
                "status": MembershipStatus.ACTIVE,
            },
        )

        store_beta, _ = Store.objects.get_or_create(
            merchant=merchant_beta,
            defaults={
                "name": "Urban Clay & Ceramics",
                "slug": "demo-urban-ceramics",
                "tagline": "Handmade Modern Stoneware & Studio Pottery",
                "description": "Earthy, food-safe tableware and functional sculptural ceramics.",
                "whatsapp_number": "+91 9123456789",
                "status": StoreStatus.PUBLISHED,
            },
        )

        # 5 Categories
        categories_data = [
            ("Dinnerware & Bowls", "dinnerware-bowls", 1),
            ("Ceramic Vases", "ceramic-vases", 2),
            ("Mugs & Drinkware", "mugs-drinkware", 3),
            ("Studio Planters", "studio-planters", 4),
            ("Serving Platters", "serving-platters", 5),
        ]
        cats = {}
        for name, slug, order in categories_data:
            cat, _ = Category.objects.get_or_create(
                merchant=merchant_beta,
                slug=slug,
                defaults={"name": name, "display_order": order, "is_active": True},
            )
            cats[slug] = cat

        # 36 Products for Store Beta
        palette = [
            (85, 75, 65),  # Clay / Earth
            (120, 130, 115),  # Sage
            (60, 70, 75),  # Charcoal
            (160, 135, 110),  # Sand
            (95, 110, 125),  # Slate Blue
        ]

        products_spec = [
            # 1. Dinnerware & Bowls (10 items)
            (
                "Hand-Glazed Ramen Bowl",
                "dinnerware-bowls",
                Decimal("699.00"),
                Decimal("899.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-001",
                "primary",
            ),
            (
                "Stoneware Pasta Plate Set",
                "dinnerware-bowls",
                Decimal("1499.00"),
                Decimal("1899.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-002",
                "primary",
            ),
            (
                "Artisan Salad Bowl with Matt Glaze",
                "dinnerware-bowls",
                Decimal("1199.00"),
                Decimal("1599.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-003",
                "multi",
            ),
            (
                "Minimalist Dinner Set (16 Piece)",
                "dinnerware-bowls",
                SENTINEL_PRICE,
                SENTINEL_MRP,
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.CONTACT_FOR_PRICE,
                "URB-DIN-004",
                "primary",
            ),
            (
                "Speckled Stoneware Cereal Bowls",
                "dinnerware-bowls",
                Decimal("899.00"),
                Decimal("1199.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-005",
                "primary",
            ),
            (
                "Rustic Terracotta Serving Bowl",
                "dinnerware-bowls",
                Decimal("599.00"),
                Decimal("799.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-006",
                "primary",
            ),
            (
                "Japanese Ceramic Noodle Bowl",
                "dinnerware-bowls",
                Decimal("799.00"),
                Decimal("999.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-007",
                "fallback_non_primary",
            ),
            (
                "Wabi-Sabi Organic Edge Platter",
                "dinnerware-bowls",
                Decimal("1399.00"),
                Decimal("1799.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-008",
                "primary",
            ),
            (
                "Charcoal Ceramic Soup Tureen",
                "dinnerware-bowls",
                Decimal("2299.00"),
                Decimal("2899.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-009",
                "zero_image",
            ),
            (
                "Oatmeal Stoneware Tapas Plates",
                "dinnerware-bowls",
                Decimal("999.00"),
                Decimal("1299.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-DIN-010",
                "primary",
            ),
            # 2. Ceramic Vases (8 items)
            (
                "Sculptural Donut Ceramic Vase",
                "ceramic-vases",
                Decimal("1299.00"),
                Decimal("1699.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-VAS-011",
                "primary",
            ),
            (
                "Ribbed Terracotta Bud Vase",
                "ceramic-vases",
                Decimal("499.00"),
                Decimal("699.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-VAS-012",
                "primary",
            ),
            (
                "Tall Nordic Fluted Vase",
                "ceramic-vases",
                Decimal("1899.00"),
                Decimal("2399.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-VAS-013",
                "multi",
            ),
            (
                "Monumental Gallery Floor Vase",
                "ceramic-vases",
                SENTINEL_PRICE,
                SENTINEL_MRP,
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.CONTACT_FOR_PRICE,
                "URB-VAS-014",
                "primary",
            ),
            (
                "Textured Matte White Amphora",
                "ceramic-vases",
                Decimal("1599.00"),
                Decimal("1999.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-VAS-015",
                "primary",
            ),
            (
                "Asymmetric Studio Ceramic Vase",
                "ceramic-vases",
                Decimal("1399.00"),
                Decimal("1799.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "URB-VAS-016",
                "primary",
            ),
            (
                "Miniature Glazed Ikebana Vase",
                "ceramic-vases",
                Decimal("599.00"),
                Decimal("799.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-VAS-017",
                "fallback_non_primary",
            ),
            (
                "Unglazed Earth Tone Vase",
                "ceramic-vases",
                Decimal("899.00"),
                Decimal("1199.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-VAS-018",
                "zero_image",
            ),
            # 3. Mugs & Drinkware (8 items)
            (
                "Studio Handled Ceramic Coffee Mug",
                "mugs-drinkware",
                Decimal("399.00"),
                Decimal("499.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-MUG-019",
                "primary",
            ),
            (
                "Stoneware Matcha Whisk Bowl",
                "mugs-drinkware",
                Decimal("799.00"),
                Decimal("999.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-MUG-020",
                "primary",
            ),
            (
                "Speckled Espresso Cup Pair",
                "mugs-drinkware",
                Decimal("599.00"),
                Decimal("799.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-MUG-021",
                "primary",
            ),
            (
                "Custom Ceramic Beer Stein Set",
                "mugs-drinkware",
                SENTINEL_PRICE,
                SENTINEL_MRP,
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.CONTACT_FOR_PRICE,
                "URB-MUG-022",
                "primary",
            ),
            (
                "Chai Kulhad Traditional Cup Set",
                "mugs-drinkware",
                Decimal("449.00"),
                Decimal("599.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-MUG-023",
                "multi",
            ),
            (
                "Drip Glaze Cappuccino Tumbler",
                "mugs-drinkware",
                Decimal("499.00"),
                Decimal("649.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-MUG-024",
                "primary",
            ),
            (
                "Cold Brew Ceramic Pitcher",
                "mugs-drinkware",
                Decimal("1299.00"),
                Decimal("1699.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-MUG-025",
                "fallback_non_primary",
            ),
            (
                "Handmade Stoneware Goblet",
                "mugs-drinkware",
                Decimal("699.00"),
                Decimal("899.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-MUG-026",
                "zero_image",
            ),
            # 4. Studio Planters (6 items)
            (
                "Mid-Century Footed Ceramic Planter",
                "studio-planters",
                Decimal("1199.00"),
                Decimal("1599.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-027",
                "primary",
            ),
            (
                "Terracotta Hanging Herb Planter",
                "studio-planters",
                Decimal("799.00"),
                Decimal("999.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-028",
                "primary",
            ),
            (
                "Large Ribbed Indoor Planter Pot",
                "studio-planters",
                Decimal("1899.00"),
                Decimal("2499.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-029",
                "primary",
            ),
            (
                "Geometric Glazed Succulent Pot",
                "studio-planters",
                Decimal("349.00"),
                Decimal("499.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-030",
                "primary",
            ),
            (
                "Concrete & Ceramic Bonsai Basin",
                "studio-planters",
                Decimal("1499.00"),
                Decimal("1999.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-031",
                "primary",
            ),
            (
                "Minimalist Wall Planter Sconce",
                "studio-planters",
                Decimal("899.00"),
                Decimal("1199.00"),
                AvailabilityMode.OUT_OF_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-032",
                "zero_image",
            ),
            # 5. Serving Platters (4 items)
            (
                "Oval Stoneware Mezze Platter",
                "serving-platters",
                Decimal("1699.00"),
                Decimal("2199.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-033",
                "primary",
            ),
            (
                "Artisanal Cheese Board with Glaze",
                "serving-platters",
                Decimal("1299.00"),
                Decimal("1699.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-034",
                "primary",
            ),
            (
                "Tiered Ceramic High Tea Stand",
                "serving-platters",
                Decimal("2499.00"),
                Decimal("3199.00"),
                AvailabilityMode.MADE_TO_ORDER,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-035",
                "primary",
            ),
            (
                "Rustic Charcuterie Long Platter",
                "serving-platters",
                Decimal("1999.00"),
                Decimal("2599.00"),
                AvailabilityMode.IN_STOCK,
                PriceDisplayMode.SHOW_PRICE,
                "URB-PLA-036",
                "primary",
            ),
        ]

        now = timezone.now()
        for idx, item in enumerate(products_spec):
            name, cat_slug, price, mrp, avail, price_mode, sku, img_mode = item
            is_avail = avail != AvailabilityMode.OUT_OF_STOCK
            slug = f"urb-{name.lower().replace(' ', '-').replace('&', 'and')[:40]}"

            product, _ = Product.objects.get_or_create(
                merchant=merchant_beta,
                sku=sku,
                defaults={
                    "name": name,
                    "slug": slug,
                    "price": price,
                    "mrp": mrp,
                    "price_display_mode": price_mode,
                    "availability_mode": avail,
                    "is_available": is_avail,
                    "status": ProductStatus.PUBLISHED,
                    "description": f"Handcrafted food-safe {name} crafted in small batches.",
                },
            )

            target_cat = cats[cat_slug]
            ProductCategory.objects.get_or_create(product=product, category=target_cat)

            staggered_date = now - timedelta(days=idx + 1, hours=(idx * 3) % 24)
            Product.objects.filter(id=product.id).update(created_at=staggered_date)

            color = palette[idx % len(palette)]
            if img_mode == "primary":
                f = generate_synthetic_placeholder(
                    name, target_cat.name, color, f"urb_{idx}_prim.jpg"
                )
                ProductImage.objects.create(
                    product=product, image=f, is_primary=True, display_order=1
                )
            elif img_mode == "multi":
                f1 = generate_synthetic_placeholder(
                    name, target_cat.name, color, f"urb_{idx}_m1.jpg"
                )
                ProductImage.objects.create(
                    product=product, image=f1, is_primary=True, display_order=1
                )
                f2 = generate_synthetic_placeholder(
                    f"{name} (Glaze)", "Macro Detail", color, f"urb_{idx}_m2.jpg"
                )
                ProductImage.objects.create(
                    product=product, image=f2, is_primary=False, display_order=2
                )
            elif img_mode == "fallback_non_primary":
                f = generate_synthetic_placeholder(
                    name, "Studio Gallery", color, f"urb_{idx}_nonprim.jpg"
                )
                ProductImage.objects.create(
                    product=product, image=f, is_primary=False, display_order=1
                )
            # zero_image mode creates 0 ProductImage instances to test neutral fallback placeholder

    def _print_verification_summary(self):
        """Displays clear summary of newly seeded demo tenants and checks existing records."""
        self.stdout.write("\n" + "=" * 65)
        self.stdout.write("              C3 DEMO SEEDING VERIFICATION REPORT             ")
        self.stdout.write("=" * 65)

        for slug in EXACT_DEMO_STORE_SLUGS:
            store = Store.objects.get(slug=slug)
            merchant = store.merchant
            products = Product.objects.filter(merchant=merchant)
            categories = Category.objects.filter(merchant=merchant)
            images = ProductImage.objects.filter(product__merchant=merchant)
            mto = products.filter(availability_mode=AvailabilityMode.MADE_TO_ORDER).count()
            oos = products.filter(availability_mode=AvailabilityMode.OUT_OF_STOCK).count()
            in_stock = products.filter(availability_mode=AvailabilityMode.IN_STOCK).count()
            cfp = products.filter(price_display_mode=PriceDisplayMode.CONTACT_FOR_PRICE).count()

            self.stdout.write(f"\n[Store]: {store.name} ({store.slug})")
            self.stdout.write(f" - URL: /s/{store.slug}/products/")
            self.stdout.write(f" - Total Published Products: {products.count()}")
            self.stdout.write(f" - Categories: {categories.count()}")
            self.stdout.write(
                f" - Availability Breakdown: In Stock ({in_stock}), Made to Order ({mto}), Out of Stock ({oos})"
            )
            self.stdout.write(
                f" - Pricing: Show Price ({products.count() - cfp}), Contact for Price ({cfp})"
            )
            self.stdout.write(f" - Images Attached: {images.count()}")

        # Unchanged real tenant guard verification
        krishna = Store.objects.filter(slug="krishnagarment").first()
        if krishna:
            k_products = Product.objects.filter(merchant=krishna.merchant).count()
            self.stdout.write(f"\n[Untouched Pre-existing Store]: {krishna.name} ({krishna.slug})")
            self.stdout.write(f" - Products: {k_products} (Confirmed completely untouched)")
        self.stdout.write("=" * 65 + "\n")
