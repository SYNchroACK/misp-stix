#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
import json
import os
import sys
from misp_stix_converter import MISPtoSTIX20Parser, MISPtoSTIX21Parser
from .test_events import *


class TestSTIX2Export(unittest.TestCase):
    _labels = [
        'Threat-Report',
        'misp:tool="MISP-STIX-Converter"'
    ]

    @staticmethod
    def _add_attribute_ids_flag(event):
        for attribute in event['Event']['Attribute']:
            attribute['to_ids'] = True

    def _check_identity_features(self, identity, orgc):
        identity_id = f"identity--{orgc['uuid']}"
        self.assertEqual(identity.type, 'identity')
        self.assertEqual(identity.id, identity_id)
        self.assertEqual(identity.name, orgc['name'])
        self.assertEqual(identity.identity_class, 'organization')
        return identity_id

    def _check_attribute_indicator_features(self, indicator, attribute, identity_id, object_ref):
        uuid = f"indicator--{attribute['uuid']}"
        self.assertEqual(uuid, object_ref)
        self.assertEqual(indicator.id, uuid)
        self.assertEqual(indicator.type, 'indicator')
        self.assertEqual(indicator.created_by_ref, identity_id)
        self._check_killchain(indicator.kill_chain_phases[0], attribute['category'])
        type_label, category_label, ids_label = indicator.labels
        self.assertEqual(type_label, f'misp:type="{attribute["type"]}"')
        self.assertEqual(category_label, f'misp:category="{attribute["category"]}"')
        self.assertEqual(ids_label, f'misp:to_ids="{attribute["to_ids"]}"')
        timestamp = self._datetime_from_timestamp(attribute['timestamp'])
        self.assertEqual(indicator.created, timestamp)
        self.assertEqual(indicator.modified, timestamp)
        self.assertEqual(indicator.valid_from, timestamp)

    def _check_killchain(self, killchain, category):
        self.assertEqual(killchain['kill_chain_name'], 'misp-category')
        self.assertEqual(killchain['phase_name'], category)

    def _check_attribute_observable_features(self, observed_data, attribute, identity_id, object_ref):
        uuid = f"observed-data--{attribute['uuid']}"
        self.assertEqual(uuid, object_ref)
        self.assertEqual(observed_data.id, uuid)
        self.assertEqual(observed_data.type, 'observed-data')
        self.assertEqual(observed_data.created_by_ref, identity_id)
        self.assertEqual(observed_data.number_observed, 1)
        type_label, category_label = observed_data.labels
        self.assertEqual(type_label, f'misp:type="{attribute["type"]}"')
        self.assertEqual(category_label, f'misp:category="{attribute["category"]}"')
        timestamp = self._datetime_from_timestamp(attribute['timestamp'])
        self.assertEqual(observed_data.created, timestamp)
        self.assertEqual(observed_data.modified, timestamp)
        self.assertEqual(observed_data.first_observed, timestamp)
        self.assertEqual(observed_data.last_observed, timestamp)

    def _check_report_features(self, report, event, identity_id, timestamp):
        self.assertEqual(report.type, 'report')
        self.assertEqual(report.id, f"report--{event['uuid']}")
        self.assertEqual(report.created_by_ref, identity_id)
        self.assertEqual(report.labels, self._labels)
        self.assertEqual(report.name, event['info'])
        self.assertEqual(report.created, timestamp)
        self.assertEqual(report.modified, timestamp)
        return report.object_refs

    @staticmethod
    def _datetime_from_timestamp(timestamp):
        return datetime.utcfromtimestamp(int(timestamp))

    @staticmethod
    def _parse_AS_value(value):
        if value.startswith('AS'):
            return int(value[2:])
        return int(value)

    @staticmethod
    def _remove_attribute_ids_flag(event):
        for attribute in event['Event']['Attribute']:
            attribute['to_ids'] = False


class TestSTIX20Export(TestSTIX2Export):
    def setUp(self):
        self.parser = MISPtoSTIX20Parser()

    def _run_indicator_tests(self, event):
        self._add_attribute_ids_flag(event)
        orgc = event['Event']['Orgc']
        attribute = event['Event']['Attribute'][0]
        self.parser.parse_misp_event(event)
        identity, report, indicator = self.parser.stix_objects
        identity_id = self._check_identity_features(identity, orgc)
        timestamp = self._datetime_from_timestamp(event['Event']['timestamp'])
        object_ref = self._check_report_features(report, event['Event'], identity_id, timestamp)[0]
        self.assertEqual(report.published, timestamp)
        self._check_attribute_indicator_features(indicator, attribute, identity_id, object_ref)
        return attribute['value'], indicator.pattern

    def _run_observable_tests(self, event):
        self._remove_attribute_ids_flag(event)
        orgc = event['Event']['Orgc']
        attribute = event['Event']['Attribute'][0]
        self.parser.parse_misp_event(event)
        identity, report, observed_data = self.parser.stix_objects
        identity_id = self._check_identity_features(identity, orgc)
        timestamp = self._datetime_from_timestamp(event['Event']['timestamp'])
        object_ref = self._check_report_features(report, event['Event'], identity_id, timestamp)[0]
        self.assertEqual(report.published, timestamp)
        self._check_attribute_observable_features(observed_data, attribute, identity_id, object_ref)
        return attribute['value'], observed_data['objects']

    def test_event_with_as_indicator_attribute(self):
        event = get_event_with_as_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        number = self._parse_AS_value(attribute_value)
        self.assertEqual(pattern, f"[autonomous-system:number = '{number}']")

    def test_event_with_as_observable_attribute(self):
        event = get_event_with_as_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        observable = observable_objects['0']
        self.assertEqual(observable.type, 'autonomous-system')
        number = self._parse_AS_value(attribute_value)
        self.assertEqual(observable.number, number)

    def test_event_with_domain_indicator_attribute(self):
        event = get_event_with_domain_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[domain-name:value = '{attribute_value}']")

    def test_event_with_domain_observable_attribute(self):
        event = get_event_with_domain_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        observable = observable_objects['0']
        self.assertEqual(observable.type, 'domain-name')
        self.assertEqual(observable.value, attribute_value)

    def test_event_with_domain_ip_indicator_attribute(self):
        event = get_event_with_domain_ip_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        domain, ip = attribute_value.split('|')
        domain_pattern = f"domain-name:value = '{domain}'"
        ip_pattern = f"domain-name:resolves_to_refs[*].value = '{ip}'"
        self.assertEqual(pattern, f'[{domain_pattern} AND {ip_pattern}]')

    def test_event_with_domain_ip_observable_attribute(self):
        event = get_event_with_domain_ip_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        domain, ip = attribute_value.split('|')
        domain_object, address_object = observable_objects.values()
        self.assertEqual(domain_object.type, 'domain-name')
        self.assertEqual(domain_object.value, domain)
        self.assertEqual(domain_object.resolves_to_refs, ['1'])
        self.assertEqual(address_object.type, 'ipv4-addr')
        self.assertEqual(address_object.value, ip)

    def test_event_with_filename_indicator_attribute(self):
        event = get_event_with_filename_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[file:name = '{attribute_value}']")

    def test_event_with_filename_observable_attribute(self):
        event = get_event_with_filename_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        observable = observable_objects['0']
        self.assertEqual(observable.type, 'file')
        self.assertEqual(observable.name, attribute_value)

    def test_event_with_hostname_indicator_attribute(self):
        event = get_event_with_hostname_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[domain-name:value = '{attribute_value}']")

    def test_event_with_hostname_observable_attribute(self):
        event = get_event_with_hostname_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        observable = observable_objects['0']
        self.assertEqual(observable.type, 'domain-name')
        self.assertEqual(observable.value, attribute_value)

    def test_event_with_hostname_port_indicator_attribute(self):
        event = get_event_with_hostname_port_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        hostname, port = attribute_value.split('|')
        hostname_pattern = f"domain-name:value = '{hostname}'"
        port_pattern = f"network-traffic:dst_port = '{port}'"
        self.assertEqual(pattern, f"[{hostname_pattern} AND {port_pattern}]")

    def test_event_with_hostname_port_observable_attribute(self):
        event = get_event_with_hostname_port_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        hostname, port = attribute_value.split('|')
        domain_object, network_traffic_object = observable_objects.values()
        self.assertEqual(domain_object.type, 'domain-name')
        self.assertEqual(domain_object.value, hostname)
        self.assertEqual(network_traffic_object.type, 'network-traffic')
        self.assertEqual(network_traffic_object.dst_port, int(port))
        self.assertEqual(network_traffic_object.dst_ref, '0')

    def test_event_with_mac_address_indicator_attribute(self):
        event = get_event_with_mac_address_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[mac-addr:value = '{attribute_value}']")

    def test_event_with_mac_address_observable_attribute(self):
        event = get_event_with_mac_address_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        observable = observable_objects['0']
        self.assertEqual(observable.type, 'mac-addr')
        self.assertEqual(observable.value, attribute_value)

    def test_event_with_mutex_indicator_attribute(self):
        event = get_event_with_mutex_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[mutex:name = '{attribute_value}']")

    def test_event_with_mutex_observable_attribute(self):
        event = get_event_with_mutex_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        observable = observable_objects['0']
        self.assertEqual(observable.type, 'mutex')
        self.assertEqual(observable.name, attribute_value)

    def test_event_with_regkey_indicator_attribute(self):
        event = get_event_with_regkey_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(
            pattern.replace('\\\\', '\\'),
            f"[windows-registry-key:key = '{attribute_value}']"
        )

    def test_event_with_regkey_observable_attribute(self):
        event = get_event_with_regkey_attribute()
        attribute_value, observable_objects = self._run_observable_tests(event)
        observable = observable_objects['0']
        self.assertEqual(observable.type, 'windows-registry-key')
        self.assertEqual(observable.key, attribute_value)


class TestSTIX21Export(TestSTIX2Export):
    def setUp(self):
        self.parser = MISPtoSTIX21Parser()

    def _check_grouping_features(self, grouping, event, identity_id):
        timestamp = self._datetime_from_timestamp(event['timestamp'])
        self.assertEqual(grouping.type, 'grouping')
        self.assertEqual(grouping.id, f"grouping--{event['uuid']}")
        self.assertEqual(grouping.created_by_ref, identity_id)
        self.assertEqual(grouping.labels, self._labels)
        self.assertEqual(grouping.name, event['info'])
        self.assertEqual(grouping.created, timestamp)
        self.assertEqual(grouping.modified, timestamp)
        return grouping.object_refs

    def _check_pattern_features(self, indicator):
        self.assertEqual(indicator.pattern_type, 'stix')
        self.assertEqual(indicator.pattern_version, '2.1')

    def _check_spec_versions(self, stix_objects):
        for stix_object in stix_objects:
            self.assertEqual(stix_object.spec_version, '2.1')

    def _run_indicator_tests(self, event):
        self._add_attribute_ids_flag(event)
        orgc = event['Event']['Orgc']
        attribute = event['Event']['Attribute'][0]
        self.parser.parse_misp_event(event)
        stix_objects = self.parser.stix_objects
        self._check_spec_versions(stix_objects)
        identity, grouping, indicator = stix_objects
        identity_id = self._check_identity_features(identity, orgc)
        args = (
            grouping,
            event['Event'],
            identity_id
        )
        object_ref = self._check_grouping_features(*args)[0]
        self._check_attribute_indicator_features(indicator, attribute, identity_id, object_ref)
        self._check_pattern_features(indicator)
        return attribute['value'], indicator.pattern

    def _run_observable_tests(self, event):
        self._remove_attribute_ids_flag(event)
        orgc = event['Event']['Orgc']
        attribute = event['Event']['Attribute'][0]
        self.parser.parse_misp_event(event)
        stix_objects = self.parser.stix_objects
        self._check_spec_versions(stix_objects)
        identity, grouping, observed_data, *observable = stix_objects
        identity_id = self._check_identity_features(identity, orgc)
        observable_id, *ids = self._check_grouping_features(
            grouping,
            event['Event'],
            identity_id
        )
        self._check_attribute_observable_features(observed_data, attribute, identity_id, observable_id)
        return attribute['value'], ids, observed_data['object_refs'], observable

    def test_event_with_as_indicator_attribute(self):
        event = get_event_with_as_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        number = self._parse_AS_value(attribute_value)
        self.assertEqual(pattern, f"[autonomous-system:number = '{number}']")

    def test_event_with_as_observable_attribute(self):
        event = get_event_with_as_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        object_ref = object_refs[0]
        AS = observable[0]
        self.assertEqual(object_ref, grouping_refs[0])
        self.assertEqual(AS.id, object_ref)
        self.assertEqual(AS.type, 'autonomous-system')
        number = self._parse_AS_value(attribute_value)
        self.assertEqual(AS.number, number)

    def test_event_with_domain_indicator_attribute(self):
        event = get_event_with_domain_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[domain-name:value = '{attribute_value}']")

    def test_event_with_domain_observable_attribute(self):
        event = get_event_with_domain_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        object_ref = object_refs[0]
        domain = observable[0]
        self.assertEqual(object_ref, grouping_refs[0])
        self.assertEqual(domain.id, object_ref)
        self.assertEqual(domain.type, 'domain-name')
        self.assertEqual(domain.value, attribute_value)

    def test_event_with_domain_ip_indicator_attribute(self):
        event = get_event_with_domain_ip_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        domain, ip = attribute_value.split('|')
        domain_pattern = f"domain-name:value = '{domain}'"
        ip_pattern = f"domain-name:resolves_to_refs[*].value = '{ip}'"
        self.assertEqual(pattern, f'[{domain_pattern} AND {ip_pattern}]')

    def test_event_with_domain_ip_observable_attribute(self):
        event = get_event_with_domain_ip_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        domain_value, ip_value = attribute_value.split('|')
        domain_id, address_id = grouping_refs
        domain_ref, address_ref = object_refs
        domain, address = observable
        self.assertEqual(domain_ref, domain_id)
        self.assertEqual(domain.id, domain_ref)
        self.assertEqual(domain.type, 'domain-name')
        self.assertEqual(domain.value, domain_value)
        self.assertEqual(domain.resolves_to_refs, [address_id])
        self.assertEqual(address_ref, address_id)
        self.assertEqual(address.id, address_ref)
        self.assertEqual(address.type, 'ipv4-addr')
        self.assertEqual(address.value, ip_value)

    def test_event_with_filename_indicator_attribute(self):
        event = get_event_with_filename_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[file:name = '{attribute_value}']")

    def test_event_with_filename_observable_attribute(self):
        event = get_event_with_filename_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        object_ref = object_refs[0]
        file = observable[0]
        self.assertEqual(object_ref, grouping_refs[0])
        self.assertEqual(file.id, object_ref)
        self.assertEqual(file.type, 'file')
        self.assertEqual(file.name, attribute_value)

    def test_event_with_hostname_indicator_attribute(self):
        event = get_event_with_hostname_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[domain-name:value = '{attribute_value}']")

    def test_event_with_hostname_observable_attribute(self):
        event = get_event_with_hostname_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        object_ref = object_refs[0]
        domain = observable[0]
        self.assertEqual(object_ref, grouping_refs[0])
        self.assertEqual(domain.id, object_ref)
        self.assertEqual(domain.type, 'domain-name')
        self.assertEqual(domain.value, attribute_value)

    def test_event_with_hostname_port_indicator_attribute(self):
        event = get_event_with_hostname_port_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        hostname, port = attribute_value.split('|')
        hostname_pattern = f"domain-name:value = '{hostname}'"
        port_pattern = f"network-traffic:dst_port = '{port}'"
        self.assertEqual(pattern, f"[{hostname_pattern} AND {port_pattern}]")

    def test_event_with_hostname_port_observable_attribute(self):
        event = get_event_with_hostname_port_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        hostname, port = attribute_value.split('|')
        domain_id, network_traffic_id = grouping_refs
        hostname_ref, network_traffic_ref = object_refs
        domain, network_traffic = observable
        self.assertEqual(hostname_ref, domain_id)
        self.assertEqual(domain.id, hostname_ref)
        self.assertEqual(domain.type, 'domain-name')
        self.assertEqual(domain.value, hostname)
        self.assertEqual(network_traffic.id, network_traffic_id)
        self.assertEqual(network_traffic.type, 'network-traffic')
        self.assertEqual(network_traffic.dst_port, int(port))
        self.assertEqual(network_traffic.dst_ref, domain_id)

    def test_event_with_mac_address_indicator_attribute(self):
        event = get_event_with_mac_address_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[mac-addr:value = '{attribute_value}']")

    def test_event_with_mac_address_observable_attribute(self):
        event = get_event_with_mac_address_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        object_ref = object_refs[0]
        mac_address = observable[0]
        self.assertEqual(object_ref, grouping_refs[0])
        self.assertEqual(mac_address.id, object_ref)
        self.assertEqual(mac_address.type, 'mac-addr')
        self.assertEqual(mac_address.value, attribute_value)

    def test_event_with_mutex_indicator_attribute(self):
        event = get_event_with_mutex_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(pattern, f"[mutex:name = '{attribute_value}']")

    def test_event_with_mutex_observable_attribute(self):
        event = get_event_with_mutex_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        object_ref = object_refs[0]
        mutex = observable[0]
        self.assertEqual(object_ref, grouping_refs[0])
        self.assertEqual(mutex.id, object_ref)
        self.assertEqual(mutex.type, 'mutex')
        self.assertEqual(mutex.name, attribute_value)

    def test_event_with_regkey_indicator_attribute(self):
        event = get_event_with_regkey_attribute()
        attribute_value, pattern = self._run_indicator_tests(event)
        self.assertEqual(
            pattern.replace('\\\\', '\\'),
            f"[windows-registry-key:key = '{attribute_value}']"
        )

    def test_event_with_regkey_observable_attribute(self):
        event = get_event_with_regkey_attribute()
        attribute_value, grouping_refs, object_refs, observable = self._run_observable_tests(event)
        object_ref = object_refs[0]
        registry_key = observable[0]
        self.assertEqual(object_ref, grouping_refs[0])
        self.assertEqual(registry_key.id, object_ref)
        self.assertEqual(registry_key.type, 'windows-registry-key')
        self.assertEqual(registry_key.key, attribute_value)