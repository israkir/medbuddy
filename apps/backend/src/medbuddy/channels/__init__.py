"""Delivery channels: LINE Messaging API vs standalone mobile HTTP.

Shared domain logic and integrations live outside this package; channel code adapts
transport and identity (webhook signatures, future app auth) to the same services.
"""
