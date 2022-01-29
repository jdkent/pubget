import logging
from typing import Dict, Union

from lxml import etree

from nqdc import _utils
from nqdc._typing import BaseExtractor

_LOG = logging.getLogger(__name__)


class TextExtractor(BaseExtractor):
    fields = ("pmcid", "title", "keywords", "abstract", "body")
    name = "text"

    def __init__(self) -> None:
        self._stylesheet = _utils.load_stylesheet("text_extraction.xsl")

    def extract(
        self, article: etree.ElementTree
    ) -> Dict[str, Union[str, int]]:
        return self._extract_text_from_article(article, self._stylesheet)

    def _extract_text_from_article(
        self, article: etree.ElementTree, stylesheet: etree.XSLT
    ) -> Dict[str, Union[str, int]]:
        result: Dict[str, Union[str, int]] = {}
        try:
            transformed = stylesheet(article)
        except Exception:
            _LOG.exception(
                f"failed to transform article: {stylesheet.error_log}"
            )
            return result
        for part_name in self.fields:
            elem = transformed.find(part_name)
            result[part_name] = elem.text
        result["pmcid"] = int(result["pmcid"])
        return result
