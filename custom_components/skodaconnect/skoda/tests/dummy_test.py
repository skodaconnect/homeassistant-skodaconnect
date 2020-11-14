import pytest
import sys
import os
from aiohttp import ClientSession

# we need to change os path to be able to import volkswagecarnet
myPath = os.path.dirname(os.path.abspath(__file__))
print(myPath)
sys.path.insert(0, myPath + '/../')


@pytest.mark.asyncio
async def test_volkswagencarnet():
    import skoda
    async with ClientSession() as session:
        connection = skoda.Connection(session, 'test@example.com', 'test_password')
        # if await connection._login():
        if not connection.logged_in:
            return True
    pytest.fail('Something happend we should have got a False from vw.logged_in')
