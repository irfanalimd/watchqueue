"""Tests for external API clients (TMDB)."""

import pytest
import respx
from httpx import Response

from app.services.external_api import TMDBClient, enrich_queue_item


class TestTMDBClient:
    """Tests for TMDB API client."""

    @respx.mock
    async def test_search_movie(self, mock_tmdb_response):
        """Test searching for a movie."""
        respx.get("https://api.themoviedb.org/3/search/movie").mock(
            return_value=Response(200, json=mock_tmdb_response)
        )

        client = TMDBClient(api_key="test_key")
        try:
            result = await client.search_movie("Inception")

            assert result is not None
            assert result.tmdb_id == 27205
            assert result.title == "Inception"
            assert result.year == 2010
            assert "tmdb.org" in result.poster_url
        finally:
            await client.close()

    @respx.mock
    async def test_search_movie_not_found(self):
        """Test searching for a movie that doesn't exist."""
        respx.get("https://api.themoviedb.org/3/search/movie").mock(
            return_value=Response(200, json={"results": []})
        )

        client = TMDBClient(api_key="test_key")
        try:
            result = await client.search_movie("NonexistentMovie12345")
            assert result is None
        finally:
            await client.close()

    @respx.mock
    async def test_get_movie_details(self, mock_tmdb_movie_details):
        """Test getting movie details by ID."""
        respx.get("https://api.themoviedb.org/3/movie/27205").mock(
            return_value=Response(200, json=mock_tmdb_movie_details)
        )

        client = TMDBClient(api_key="test_key")
        try:
            result = await client.get_movie(27205)

            assert result is not None
            assert result.tmdb_id == 27205
            assert result.runtime_minutes == 148
            assert "Action" in result.genres
            assert "Science Fiction" in result.genres
        finally:
            await client.close()

    @respx.mock
    async def test_api_error_handling(self):
        """Test graceful handling of API errors."""
        respx.get("https://api.themoviedb.org/3/search/movie").mock(
            return_value=Response(500, json={"status_message": "Internal error"})
        )

        client = TMDBClient(api_key="test_key")
        try:
            result = await client.search_movie("Inception")
            assert result is None  # Should return None on error, not raise
        finally:
            await client.close()

    async def test_no_api_key(self):
        """Test behavior when API key is not configured."""
        client = TMDBClient(api_key="")
        try:
            result = await client.search_movie("Inception")
            assert result is None
        finally:
            await client.close()

    @respx.mock
    async def test_search_tv(self):
        """Test searching for a TV show."""
        respx.get("https://api.themoviedb.org/3/search/tv").mock(
            return_value=Response(200, json={
                "results": [{
                    "id": 1399,
                    "name": "Game of Thrones",
                    "poster_path": "/poster.jpg",
                    "first_air_date": "2011-04-17",
                    "overview": "Seven noble families...",
                }]
            })
        )

        client = TMDBClient(api_key="test_key")
        try:
            result = await client.search_tv("Game of Thrones")

            assert result is not None
            assert result.tmdb_id == 1399
            assert result.title == "Game of Thrones"
            assert result.year == 2011
        finally:
            await client.close()


class TestEnrichQueueItem:
    """Tests for queue item enrichment."""

    @respx.mock
    async def test_enrich_success(self, mock_tmdb_response):
        """Test successful enrichment."""
        respx.get("https://api.themoviedb.org/3/search/movie").mock(
            return_value=Response(200, json=mock_tmdb_response)
        )
        respx.get("https://api.themoviedb.org/3/movie/27205/watch/providers").mock(
            return_value=Response(
                200,
                json={
                    "id": 27205,
                    "results": {
                        "US": {
                            "link": "https://www.themoviedb.org/movie/27205/watch",
                            "flatrate": [
                                {
                                    "provider_name": "Netflix",
                                    "logo_path": "/logo.png",
                                }
                            ],
                        }
                    },
                },
            )
        )

        tmdb_client = TMDBClient(api_key="test_key")
        try:
            result = await enrich_queue_item("Inception", tmdb_client=tmdb_client)

            assert "tmdb_id" in result
            assert result["tmdb_id"] == 27205
            assert "poster_url" in result
            assert "year" in result
            assert result["play_now_url"] == "https://www.themoviedb.org/movie/27205/watch"
            assert "Netflix" in result["streaming_on"]
            assert result["provider_links"][0]["provider_name"] == "Netflix"
        finally:
            await tmdb_client.close()

    @respx.mock
    async def test_enrich_graceful_degradation(self):
        """Test that enrichment fails gracefully when API is down."""
        respx.get("https://api.themoviedb.org/3/search/movie").mock(
            return_value=Response(500)
        )

        tmdb_client = TMDBClient(api_key="test_key")
        try:
            result = await enrich_queue_item("Inception", tmdb_client=tmdb_client)

            # Should return empty dict, not raise
            assert isinstance(result, dict)
        finally:
            await tmdb_client.close()
