from pathlib import Path
import logging
import json
from contextlib import ExitStack
from typing import Generator, Dict, Optional, Tuple, Any, List

from lxml import etree

from nqdc._coordinates import CoordinateExtractor
from nqdc._metadata import MetadataExtractor
from nqdc._text import TextExtractor
from nqdc._writers import CSVWriter
from nqdc._typing import PathLikeOrStr, BaseExtractor, BaseWriter
from nqdc import _utils


_LOG = logging.getLogger(__name__)


def extract_data(
    articles_dir: PathLikeOrStr, *, articles_with_coords_only: bool = True
) -> Generator[Dict[str, Any], None, None]:
    """Extract text and coordinates from articles.

    Parameters
    ----------
    articles_dir
        Directory containing the article files. It is a directory created by
        `nqdc.extract_articles`: it is named `articles` and contains
        subdirectories `000` - `fff`, each of which contains articles stored in
        XML files.
    articles_with_coords_only
        If true, articles that contain no stereotactic coordinates are ignored.

    Yields
    ------
    article_data
        Data extracted from one article. Keys are:
        - metadata: a dictionary containing metadata such as pmcid and doi.
        - text: a dictionary mapping parts such as "abstract" to their content.
        - coordinates: a `pd.DataFrame` containing the extracted coordinates.
    """
    articles_dir = Path(articles_dir)
    _utils.assert_exists(articles_dir)
    data_extractors: List[BaseExtractor] = [
        CoordinateExtractor(),
        MetadataExtractor(),
        TextExtractor(),
    ]
    for article in iter_articles(articles_dir):
        yield {
            extractor.name: extractor.extract(article)
            for extractor in data_extractors
        }


def iter_articles(
    articles_dir: PathLikeOrStr,
) -> Generator[etree.ElementTree, None, None]:
    """Generator that iterates over all articles in a directory.

    Articles are parsed and provided as ElementTrees. Articles that fail to be
    parsed are skipped. The order in which articles are visited is
    deterministic.

    Parameters
    ----------
    articles_dir
        Directory containing the article files. It is a directory created by
        `nqdc.extract_articles`: it is named `articles` and contains
        subdirectories `000` - `fff`, each of which contains articles stored in
        XML files.

    Yields
    ------
    article
        A parsed article.
    """
    articles_dir = Path(articles_dir)
    _utils.assert_exists(articles_dir)
    n_articles, n_failures = 0, 0
    for subdir in sorted([f for f in articles_dir.glob("*") if f.is_dir()]):
        for article_file in sorted(subdir.glob("pmcid_*.xml")):
            try:
                article = etree.parse(str(article_file))
            except Exception:
                n_failures += 1
                _LOG.exception(f"Failed to parse {article_file}")
            else:
                yield article
            finally:
                n_articles += 1
                if not n_articles % 20:
                    _LOG.info(
                        f"In directory {subdir.name}: "
                        f"processed {n_articles} articles, "
                        f"{n_failures} failures"
                    )


def _get_output_dir(
    articles_dir: PathLikeOrStr,
    output_dir: Optional[PathLikeOrStr],
    articles_with_coords_only: bool,
) -> Path:
    if output_dir is None:
        articles_dir = Path(articles_dir)
        subset_name = (
            "articlesWithCoords"
            if articles_with_coords_only
            else "allArticles"
        )
        output_dir = articles_dir.with_name(
            f"subset_{subset_name}_extractedData"
        )
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    return output_dir


def extract_data_to_csv(
    articles_dir: PathLikeOrStr,
    output_dir: Optional[PathLikeOrStr] = None,
    *,
    articles_with_coords_only: bool = False,
) -> Tuple[Path, int]:
    """Extract text and coordinates from articles and store in csv files.

    Parameters
    ----------
    articles_dir
        Directory containing the article files. It is a directory created by
        `nqdc.extract_articles`: it is named `articles` and contains
        subdirectories `000` - `fff`, each of which contains articles stored in
        XML files.
    output_dir
        Directory in which to store the extracted data. If not specified, a
        sibling directory of `articles_dir` is used. Its name is
        `subset_allArticles_extractedData` or
        `subset_articlesWithCoords_extractedData`, depending on the value of
        `articles_with_coords_only`.
    articles_with_coords_only
        If true, articles that contain no stereotactic coordinates are ignored.

    Returns
    -------
    output_dir
        The directory in which extracted data is stored.
    exit_code
        Always 0 at the moment. Used by the `nqdc` command-line interface.
    """
    _utils.assert_exists(Path(articles_dir))
    output_dir = _get_output_dir(
        articles_dir, output_dir, articles_with_coords_only
    )
    _LOG.info(
        f"Extracting data from articles in {articles_dir} to {output_dir}"
    )
    all_writers: List[BaseWriter] = [
        CSVWriter.from_extractor(MetadataExtractor, output_dir),
        CSVWriter.from_extractor(TextExtractor, output_dir),
        CSVWriter.from_extractor(CoordinateExtractor, output_dir),
    ]
    with ExitStack() as stack:
        for writer in all_writers:
            stack.enter_context(writer)
        n_articles = 0
        for article_data in extract_data(
            articles_dir, articles_with_coords_only=articles_with_coords_only
        ):
            n_articles += 1
            for writer in all_writers:
                writer.write(article_data)
    output_dir.joinpath("info.json").write_text(
        json.dumps({"n_articles": n_articles}), "utf-8"
    )
    _LOG.info(f"Done extracting article data to csv files in {output_dir}")
    return output_dir, 0
