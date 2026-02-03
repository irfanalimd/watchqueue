"""External API clients for movie/show metadata."""

import asyncio
from dataclasses import dataclass
from typing import Any
import httpx
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class MovieInfo:
    """Movie information from TMDB."""
    tmdb_id: int
    title: str
    poster_url: str | None
    year: int | None
    runtime_minutes: int | None
    genres: list[str]
    overview: str | None
    vote_average: float | None = None


@dataclass
class StreamingInfo:
    """Streaming availability information."""
    provider_name: str
    provider_logo: str | None
    link: str | None


class TMDBClient:
    """Client for The Movie Database API.

    Handles fetching movie/show metadata including posters, genres, runtime.
    """

    _genre_cache: dict[int, str] = {}

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.tmdb_api_key
        self.base_url = base_url or settings.tmdb_base_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=10.0,
                params={"api_key": self.api_key},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search_movie(self, query: str) -> MovieInfo | None:
        """Search for a movie by title.

        Returns the first matching result.
        """
        if not self.api_key:
            logger.warning("TMDB API key not configured")
            return None

        try:
            client = await self._get_client()
            response = await client.get(
                "/search/movie",
                params={"query": query},
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                return None

            movie = results[0]
            return await self._parse_movie(movie)

        except httpx.HTTPError as e:
            logger.error(f"TMDB search failed: {e}")
            return None

    async def get_genre_map(self) -> dict[int, str]:
        """Get cached genre ID to name mapping from TMDB."""
        if TMDBClient._genre_cache:
            return TMDBClient._genre_cache
        if not self.api_key:
            return {}
        try:
            client = await self._get_client()
            response = await client.get("/genre/movie/list")
            response.raise_for_status()
            for g in response.json().get("genres", []):
                TMDBClient._genre_cache[g["id"]] = g["name"]
            # Also fetch TV genres
            response = await client.get("/genre/tv/list")
            response.raise_for_status()
            for g in response.json().get("genres", []):
                if g["id"] not in TMDBClient._genre_cache:
                    TMDBClient._genre_cache[g["id"]] = g["name"]
        except httpx.HTTPError as e:
            logger.error(f"TMDB genre fetch failed: {e}")
        return TMDBClient._genre_cache

    async def search_multi(self, query: str, limit: int = 8) -> list[MovieInfo]:
        """Search TMDB for movies and TV shows, returning multiple results."""
        if not self.api_key:
            logger.warning("TMDB API key not configured")
            return []

        try:
            client = await self._get_client()
            genre_map = await self.get_genre_map()

            response = await client.get(
                "/search/multi",
                params={"query": query},
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for item in data.get("results", []):
                media_type = item.get("media_type")
                if media_type == "movie":
                    poster_path = item.get("poster_path")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                    release_date = item.get("release_date", "")
                    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
                    genres = [genre_map[gid] for gid in item.get("genre_ids", []) if gid in genre_map]
                    results.append(MovieInfo(
                        tmdb_id=item["id"],
                        title=item.get("title", ""),
                        poster_url=poster_url,
                        year=year,
                        runtime_minutes=None,
                        genres=genres,
                        overview=item.get("overview"),
                        vote_average=item.get("vote_average"),
                    ))
                elif media_type == "tv":
                    poster_path = item.get("poster_path")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                    first_air = item.get("first_air_date", "")
                    year = int(first_air[:4]) if first_air and len(first_air) >= 4 else None
                    genres = [genre_map[gid] for gid in item.get("genre_ids", []) if gid in genre_map]
                    results.append(MovieInfo(
                        tmdb_id=item["id"],
                        title=item.get("name", item.get("original_name", "")),
                        poster_url=poster_url,
                        year=year,
                        runtime_minutes=None,
                        genres=genres,
                        overview=item.get("overview"),
                        vote_average=item.get("vote_average"),
                    ))

                if len(results) >= limit:
                    break

            return results

        except httpx.HTTPError as e:
            logger.error(f"TMDB multi search failed: {e}")
            return []

    async def get_movie(self, tmdb_id: int) -> MovieInfo | None:
        """Get movie details by TMDB ID."""
        if not self.api_key:
            logger.warning("TMDB API key not configured")
            return None

        try:
            client = await self._get_client()
            response = await client.get(f"/movie/{tmdb_id}")
            response.raise_for_status()

            movie = response.json()
            return await self._parse_movie(movie, full_details=True)

        except httpx.HTTPError as e:
            logger.error(f"TMDB get movie failed: {e}")
            return None

    async def _parse_movie(
        self,
        movie: dict[str, Any],
        full_details: bool = False,
    ) -> MovieInfo:
        """Parse movie data from TMDB response."""
        poster_path = movie.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        release_date = movie.get("release_date", "")
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None

        # Genre names come differently in search vs details
        if full_details:
            genres = [g["name"] for g in movie.get("genres", [])]
            runtime = movie.get("runtime")
        else:
            genres = []  # Search results only have genre_ids
            runtime = None

        return MovieInfo(
            tmdb_id=movie["id"],
            title=movie["title"],
            poster_url=poster_url,
            year=year,
            runtime_minutes=runtime,
            genres=genres,
            overview=movie.get("overview"),
        )

    async def search_tv(self, query: str) -> MovieInfo | None:
        """Search for a TV show by title."""
        if not self.api_key:
            return None

        try:
            client = await self._get_client()
            response = await client.get(
                "/search/tv",
                params={"query": query},
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                return None

            show = results[0]
            return await self._parse_tv(show)

        except httpx.HTTPError as e:
            logger.error(f"TMDB TV search failed: {e}")
            return None

    async def _parse_tv(self, show: dict[str, Any]) -> MovieInfo:
        """Parse TV show data from TMDB response."""
        poster_path = show.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        first_air = show.get("first_air_date", "")
        year = int(first_air[:4]) if first_air and len(first_air) >= 4 else None

        return MovieInfo(
            tmdb_id=show["id"],
            title=show.get("name", show.get("original_name", "")),
            poster_url=poster_url,
            year=year,
            runtime_minutes=None,  # TV shows don't have a single runtime
            genres=[],
            overview=show.get("overview"),
        )

    async def search(self, query: str) -> MovieInfo | None:
        """Search for a movie or TV show.

        Searches movies first, falls back to TV if no results.
        """
        result = await self.search_movie(query)
        if result:
            return result
        return await self.search_tv(query)


class StreamingAvailabilityClient:
    """Client for checking streaming availability.

    Note: JustWatch doesn't have a public API, so this is a placeholder
    that could be implemented with a third-party service or scraping solution.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_availability(self, title: str) -> list[str]:
        """Get streaming availability for a title.

        Returns list of provider names where the title is available.
        This is a placeholder - implement with actual API.
        """
        # Placeholder implementation
        # In production, integrate with a streaming availability API
        return []

    async def check_provider(self, title: str, provider: str) -> bool:
        """Check if title is available on specific provider."""
        availability = await self.get_availability(title)
        return provider.lower() in [p.lower() for p in availability]


async def enrich_queue_item(
    title: str,
    tmdb_client: TMDBClient | None = None,
    streaming_client: StreamingAvailabilityClient | None = None,
) -> dict[str, Any]:
    """Fetch movie details from multiple sources concurrently.

    Returns enrichment data that can be used to update a queue item.
    Handles failures gracefully - returns partial data if some APIs fail.
    """
    own_tmdb = tmdb_client is None
    own_streaming = streaming_client is None

    if own_tmdb:
        tmdb_client = TMDBClient()
    if own_streaming:
        streaming_client = StreamingAvailabilityClient()

    try:
        # Fetch from both sources concurrently
        tmdb_task = asyncio.create_task(tmdb_client.search(title))
        streaming_task = asyncio.create_task(streaming_client.get_availability(title))

        movie_info, streaming = await asyncio.gather(
            tmdb_task,
            streaming_task,
            return_exceptions=True,
        )

        result: dict[str, Any] = {}

        # Handle TMDB results
        if isinstance(movie_info, MovieInfo):
            result["tmdb_id"] = movie_info.tmdb_id
            result["poster_url"] = movie_info.poster_url
            result["year"] = movie_info.year
            result["runtime_minutes"] = movie_info.runtime_minutes
            result["genres"] = movie_info.genres
        elif isinstance(movie_info, Exception):
            logger.warning(f"TMDB enrichment failed for '{title}': {movie_info}")

        # Handle streaming results
        if isinstance(streaming, list):
            result["streaming_on"] = streaming
        elif isinstance(streaming, Exception):
            logger.warning(f"Streaming enrichment failed for '{title}': {streaming}")

        return result

    finally:
        if own_tmdb:
            await tmdb_client.close()
        if own_streaming:
            await streaming_client.close()
