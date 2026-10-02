"""Offline price-ingestion utilities for the EX-Graph macro/market layer.

This package only validates/normalizes local input files. It must NOT call any
external price API or download service; data files are expected to already
exist under data/raw/prices/.
"""
