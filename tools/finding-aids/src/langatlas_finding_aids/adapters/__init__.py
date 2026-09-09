"""One adapter per finding aid. Two read a monthly mirror; two call a live API. They share
a return type (`FindingAidResult`) and nothing else — pretending four very different
backends are symmetric would mean either faking an API over two static sources or
crippling the two real ones (D53 §O2)."""
