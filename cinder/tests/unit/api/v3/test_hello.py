# Copyright 2026
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Unit tests for the hello world API controller."""

import unittest

try:
    from cinder.api.v3 import hello
except ImportError:
    hello = None


class HelloControllerTest(unittest.TestCase):
    def setUp(self):
        super(HelloControllerTest, self).setUp()
        if hello is not None:
            self.controller = hello.HelloController()

    def test_hello_module_exists(self):
        self.assertIsNotNone(
            hello, 'cinder.api.v3.hello 模块应存在并注册到 v3 API')

    def test_index_returns_hello_world(self):
        self.assertIsNotNone(hello, 'hello 模块缺失')
        self.assertEqual(
            {'message': 'Hello, World!'}, self.controller.index(None))

    def test_index_returns_only_message_key(self):
        self.assertIsNotNone(hello, 'hello 模块缺失')
        result = self.controller.index(None)
        self.assertEqual({'message'}, set(result.keys()))

    def test_index_does_not_require_auth_context(self):
        self.assertIsNotNone(hello, 'hello 模块缺失')
        result = self.controller.index(None)
        self.assertEqual('Hello, World!', result['message'])

    def test_create_resource(self):
        self.assertIsNotNone(hello, 'hello 模块缺失')
        self.assertIsNotNone(hello.create_resource())


if __name__ == '__main__':
    unittest.main()
