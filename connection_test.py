"""Read-only connection check for public Bershka product pages."""
import json
import re
from urllib.parse import urlsplit, parse_qs

CASES = (("243093353", "800"), ("228309062", "400"))

def interpret_size(label, description, disabled):
    label = label.strip()
    desc = description.casefold()
    if not label:
        raise ValueError("Missing size label")
    if "tükendi" in desc or "out of stock" in desc:
        return label, "out_of_stock"
    if "yakında" in desc or "coming soon" in desc:
        return label, "coming_soon"
    return label, "unknown" if disabled else "selectable"

def collect_offers(documents):
    offers = []
    for raw in documents:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
            continue
        records = data.get("offers", [])
        if isinstance(records, dict):
            records = [records]
        for offer in records:
            if not isinstance(offer, dict):
                continue
            if offer.get("priceCurrency") != "TRY" or offer.get("eligibleRegion") != "TR":
                continue
            sku = offer.get("sku")
            status = str(offer.get("availability", "")).rsplit("/", 1)[-1]
            if sku and status in ("InStock", "OutOfStock", "LimitedAvailability", "PreOrder"):
                offers.append({"sku": sku, "availability": status, "price": offer.get("price"), "currency": "TRY"})
    return offers

def valid_page(url, product, color):
    p = urlsplit(url)
    return (p.scheme == "https" and p.hostname == "www.bershka.com"
            and p.path.startswith("/tr/") and p.path.endswith("p" + product + ".html")
            and parse_qs(p.query).get("colorId") == [color])

def check(driver, product, color):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    url = f"https://www.bershka.com/tr/c0p{product}.html?colorId={color}"
    driver.get(url)
    print("Page:", driver.current_url, "Title:", driver.title, flush=True)
    if not valid_page(driver.current_url, product, color):
        raise RuntimeError("Unexpected product or color URL")
    body = driver.find_element(By.TAG_NAME, "body").text[:3000].casefold()
    if any(term in body for term in ("access denied", "request blocked", "forbidden", "too many requests", "captcha")):
        raise RuntimeError("Access restricted; stopping")
    WebDriverWait(driver, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "button.size-button .size-button__label")
    )
    sizes = {}
    for b in driver.find_elements(By.CSS_SELECTOR, "button.size-button"):
        labels = b.find_elements(By.CSS_SELECTOR, ".size-button__label")
        if not labels:
            continue
        label, state = interpret_size(
            labels[0].get_attribute("textContent") or "",
            b.get_attribute("aria-description") or "",
            not b.is_enabled() or b.get_attribute("aria-disabled") == "true",
        )
        if label in sizes and sizes[label] != state:
            raise RuntimeError("Conflicting size observations")
        sizes[label] = state
    offers = collect_offers([
        s.get_attribute("textContent")
        for s in driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]')
    ])
    result = {"product": product, "color": color, "sizes": sizes, "offers": offers}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if not sizes or not offers or all(s == "unknown" for s in sizes.values()):
        raise RuntimeError("Insufficient stock evidence")
    return result

def main():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(40)
    try:
        for product, color in CASES:
            check(driver, product, color)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
