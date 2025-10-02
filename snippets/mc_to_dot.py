import requests
from bs4 import BeautifulSoup


def mc_to_dot(mc_number: str) -> str | None:
    """
    Convert an MC number to a DOT number using FMCSA SAFER search.
    Returns DOT number as string or None if not found.
    """
    url = f"https://safer.fmcsa.dot.gov/CompanySnapshot.aspx?query_string={mc_number}&query_type=MC"
    resp = requests.get(url)

    if resp.status_code != 200:
        print("Error: FMCSA request failed.")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text()

    # Very rough: find DOT number pattern in page text
    # DOT numbers are 5–8 digits
    import re

    match = re.search(r"USDOT Number: (\d+)", text)
    if match:
        return match.group(1)

    return None


# Example usage
if __name__ == "__main__":
    dot_number = mc_to_dot("123456")  # replace with real MC number
    print("DOT Number:", dot_number)
