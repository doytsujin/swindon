import pytest
from unittest import mock
from async_timeout import timeout
from aiohttp import web
from aiohttp import WSMsgType
from aiohttp.web import json_response


async def test_simple_userinfo(proxy_server, swindon):
    url = swindon.url / 'swindon-chat'
    async with proxy_server.swindon_chat(url, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'
        assert req.headers['Content-Type'] == 'application/json'
        assert 'Authorization' not in req.headers
        expected = [
            {'connection_id': '0'},
            [],
            {'http_cookie': None,
             'http_authorization': None,
             'url_querystring': '',
             }]
        assert await req.json() == expected

        fut.set_result(
            web.Response(text='{"user_id": "user:1", "username": "John"}'))
        ws = await inflight.client_resp
        msg = await ws.receive_json()
        assert msg == ['hello', {}, {'user_id': 'user:1', 'username': 'John'}]


async def test_ws_close_timeout(proxy_server, swindon):
    url = swindon.url / 'swindon-chat'
    with timeout(1):
        async with proxy_server.swindon_chat(url) as inflight:
            req, fut = await inflight.req.get()
            assert req.path == '/tangle/authorize_connection'
            fut.set_result(
                web.Response(text='{"user_id": "user:1"}'))
            ws = await inflight.client_resp
            msg = await ws.receive_json()
            assert msg == [
                'hello', {}, {'user_id': 'user:1'}]


@pytest.mark.parametrize('status_code', [
    400, 401, 404, 410, 500, 503])
async def test_error_codes(proxy_server, swindon, loop, status_code):
    url = swindon.url / 'swindon-chat'
    async with proxy_server.swindon_chat(url, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'
        fut.set_result(
            web.Response(status=status_code, body=b'Custom Error'))
        ws = await inflight.client_resp
        msg = await ws.receive()
        assert msg.type == WSMsgType.CLOSE
        assert msg.data == 4000 + status_code
        assert msg.extra == 'backend_error'
        assert ws.closed
        assert ws.close_code == 4000 + status_code


@pytest.mark.parametrize('status_code', [
    100, 101,
    201, 204,
    300, 301, 302, 304,
    402, 405,
    501, 502, 504,  # these codes are not exposed to end-user.
    ])
@pytest.mark.parametrize('body', [b'no body', b'{"user_id": "user:1"}'])
async def test_unexpected_responses(
        proxy_server, swindon, loop, status_code, body):
    url = swindon.url / 'swindon-chat'
    async with proxy_server.swindon_chat(url, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'
        fut.set_result(
            web.Response(status=status_code, body=body))
        ws = await inflight.client_resp
        msg = await ws.receive()
        assert msg.type == WSMsgType.CLOSE
        assert msg.data == 4500
        assert msg.extra == 'backend_error'
        assert ws.closed
        assert ws.close_code == 4500


@pytest.mark.parametrize('auth_resp', [
    'invalid json',
    '["user_id", "user:1"]',  # list instead of dict
    '"user:123"',
    '{}',
    '{"user_id": null}',
    '{"user_id": 123.1}',
    '{"user_id": "123",}',  # trailing comma
    ])
async def test_invalid_auth_response(proxy_server, swindon, auth_resp):
    url = swindon.url / 'swindon-chat'
    async with proxy_server.swindon_chat(url, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'

        fut.set_result(
            web.Response(text=auth_resp, content_type='application/json'))
        ws = await inflight.client_resp
        msg = await ws.receive()
        assert msg.type == WSMsgType.CLOSE
        assert msg.data == 4500
        assert msg.extra == 'backend_error'
        assert ws.closed
        assert ws.close_code == 4500


async def test_auth_request__cookies(proxy_server, swindon):
    url = swindon.url / 'swindon-chat'
    h = {"Cookie": "valid=cookie; next=value"}
    call = proxy_server.swindon_chat
    async with call(url, headers=h, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'
        assert req.headers['Content-Type'] == 'application/json'
        assert 'Authorization' not in req.headers
        expected = [
            {'connection_id': mock.ANY},
            [],
            {'http_cookie': "valid=cookie; next=value",
             'http_authorization': None,
             'url_querystring': '',
             }]
        assert await req.json() == expected

        fut.set_result(
            json_response({"user_id": "user:1", "username": "John"}))
        ws = await inflight.client_resp
        msg = await ws.receive_json()
        assert msg == ['hello', {}, {'user_id': 'user:1', 'username': 'John'}]


async def test_auth_request__querystring(proxy_server, swindon):
    url = (swindon.url / 'swindon-chat').with_query(
        'query=param1&query=param2')
    print(url)
    call = proxy_server.swindon_chat
    async with call(url, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'
        assert req.headers['Content-Type'] == 'application/json'
        assert 'Authorization' not in req.headers
        expected = [
            {'connection_id': mock.ANY},
            [],
            {'http_cookie': None,
             'http_authorization': None,
             'url_querystring': 'query=param1&query=param2',
             }]
        assert await req.json() == expected

        fut.set_result(
            json_response({"user_id": "user:1", "username": "John"}))
        ws = await inflight.client_resp
        msg = await ws.receive_json()
        assert msg == ['hello', {}, {'user_id': 'user:1', 'username': 'John'}]


async def test_auth_request__authorization(proxy_server, swindon):
    url = swindon.url / 'swindon-chat'
    h = {"Authorization": "digest abcdef"}
    call = proxy_server.swindon_chat
    async with call(url, headers=h, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'
        assert req.headers['Content-Type'] == 'application/json'
        assert 'Authorization' not in req.headers
        expected = [
            {'connection_id': mock.ANY},
            [],
            {'http_cookie': None,
             'http_authorization': "digest abcdef",
             'url_querystring': '',
             }]
        assert await req.json() == expected

        fut.set_result(json_response({
            "user_id": "user:1", "username": "John"}))
        ws = await inflight.client_resp
        msg = await ws.receive_json()
        assert msg == ['hello', {}, {'user_id': 'user:1', 'username': 'John'}]


async def test_auth_request__all(proxy_server, swindon):
    url = swindon.url / 'swindon-chat'
    url = url.with_query("foo=bar")
    h = {"Cookie": "valid=cookie", "Authorization": "digest abcdef"}
    call = proxy_server.swindon_chat
    async with call(url, headers=h, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'
        assert req.headers['Content-Type'] == 'application/json'
        assert 'Authorization' not in req.headers
        expected = [
            {'connection_id': mock.ANY},
            [],
            {'http_cookie': "valid=cookie",
             'http_authorization': "digest abcdef",
             'url_querystring': 'foo=bar',
             }]
        assert await req.json() == expected

        fut.set_result(
            json_response({"user_id": "user:1", "username": "John"}))
        ws = await inflight.client_resp
        msg = await ws.receive_json()
        assert msg == ['hello', {}, {'user_id': 'user:1', 'username': 'John'}]


async def test_echo_messages(proxy_server, swindon):
    url = swindon.url / 'swindon-chat'
    async with proxy_server.swindon_chat(url, timeout=1) as inflight:
        req, fut = await inflight.req.get()
        assert req.path == '/tangle/authorize_connection'
        fut.set_result(json_response({
            "user_id": "user:2", "username": "Jack"}))
        ws = await inflight.client_resp
        hello = await ws.receive_json()
        assert hello == [
            'hello', {}, {'user_id': 'user:2', 'username': 'Jack'}]

        ws.send_json(['chat.echo_message', {'request_id': '1'},
                      ['some message'], {}])
        req, fut = await inflight.req.get()
        assert req.path == '/chat/echo_message'
        assert await req.json() == [
            {'request_id': '1', 'connection_id': mock.ANY},
            ['some message'],
            {},
        ]
        fut.set_result(json_response({
            'echo': "some message",
            }))

        echo = await ws.receive_json()
        # XXX: connection_id must be absent!
        assert echo == [
            'result', {'request_id': '1'},
            {'echo': "some message"},
            ]