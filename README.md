BuyWithDigikala (BWDK) Python SDK
==================================
A Python SDK for integrating with the BuyWithDigikala (خرید با دیجی‌کالا) service.

Usage:
```
    from bwdk_sdk import BWDKClient, OrderItem, ItemOption

    client = BWDKClient(api_key="your_api_key_here")

    # Create an order
    items = [
        OrderItem(
            name="گوشی موبایل اپل iPhone 17 Pro Max",
            primary_amount=140000,
            amount=120000,
            count=1,
            discount_amount=22500,
            tax_amount=0,
            image_link="https://example.com/img.jpg",
            options=[
                ItemOption(type_name="color", name="قرمز", value="#FF0000", is_color=True),
                ItemOption(type_name="size", name="سایز", value="xl", is_color=False),
            ]
        )
    ]

    response = client.create_order(
        merchant_unique_id="unique-id-123",
        merchant_order_id="ORDER-001",
        main_amount=180000,
        final_amount=165000,
        discount_amount=30000,
        tax_amount=15000,
        callback_url="https://yourstore.com/bwdk/callback/",
        reservation_expired_at=1761120855,
        items=items,
    )

    print(response.order_start_url)
```
