from pathlib import Path
import xml.etree.ElementTree as Et
import argparse
import json
import subprocess


def get_derived_index(derived: str, peripherals: list):
    for i in range(len(peripherals)):
        addresses = peripherals[i]['derived']
        for address in addresses:
            if derived == address['name']:
                return i
    return None


def process_description(description: str):
    while True:
        begin = description.find('\n')
        if begin != -1:
            end = begin
            for i in range(begin + 1, len(description)):
                if description[i] != ' ':
                    end = i
                    break
            temp = description[:begin] + description[end - 1:]
            description = temp
        else:
            break
    return description


def process_values(width: int):
    values = []
    if width < 4:
        for i in range(0, int(pow(2,width))):
            name = f'Value{i}'
            description = f'Some description of {name}'
            values.append({'name': name, 'description': description, 'value': i})
    return values


def process_fields(register: str, tree: Et.Element):
    fields = []
    if tree is not None:
        for branch in tree:
            name = branch.find('name').text.upper()
            description = process_description(branch.find('description').text.capitalize())
            offset = int(branch.find('bitOffset').text, 10)
            width = int(branch.find('bitWidth').text, 10)
            access = 'RW' if branch.find('access') is None or branch.find('access').text == 'read-write' else 'RO' if branch.find('access').text == "read-only" else 'WO'
            values = process_values(width)
            if register != name:
                fields.append({'name': name,  'description': description, 'offset': offset, 'width': width, 'access': access, 'values': values })
    return fields


def process_registers(tree: Et.Element):
    registers = []
    if tree is not None:
        for branch in tree:
            name = branch.find('name').text.upper()
            description = process_description(branch.find('description').text.capitalize())
            offset = '0' if int(branch.find('addressOffset').text, 16) == 0 else f'0x{int(branch.find('addressOffset').text, 16):02X}'
            width = int(branch.find('size').text, 16)
            length = 0 if branch.attrib == {} else int(branch.attrib['array'])
            access = 'RW' if branch.find('access') is None or branch.find('access').text == 'read-write' else 'RO' if branch.find('access').text == "read-only" else 'WO'
            fields = process_fields(name, branch.find('fields'))
            registers.append({ 'name': name, 'description': description, 'offset': offset, 'width': width, 'length': length, 'access': access, 'fields': fields })
    return registers


def generate_names(peripheral: str, elements: list):
    text = ''
    for element in elements:
        name = element['name']
        name_str = f'{name.lower()}_name[]'
        if peripheral == '':
            text += f'static inline char {name_str} = "{name}";\n'
        else:
            text += f'static inline char {name_str} = "{peripheral}::{name}";\n'
    return '' if not len(elements) else text[:-1]


def run_clang_format(file: Path):
    subprocess.call(
        ['C:/Program Files/LLVM/bin/clang-format.exe', '--style=file', '-i', str(file).replace('\\','/')])


def create_base_files(namespace: str, peripherals: list, config: dict):
    Path(config['root']['base']).mkdir(parents=True, exist_ok=True)
    for peripheral in peripherals:
        registers = peripheral['registers']

        # Generate address list for base template
        addresses = ''
        for i, register in enumerate(registers):
            begin = f'{registers[0]['name'].lower()}_address'
            if i == 0:
                addresses += f'auto {begin},\n'
            else:
                addresses += f'auto {register['name'].lower()}_address = {begin} + 0x{int(register['offset'], 16):02X},\n'

        # Generate register name variables
        register_names = generate_names(peripheral['name'], peripheral['registers'])

        # Generate types for arrays of registers
        array_types = ''
        for register in registers:
            if register['length']:
                array_types += f'using {register['name']}_t = RegisterArray<{register['name'].lower()}_address, {register['width']}, {register['length']}, {register['access']}, Target, STM32F4xxx, {register['name'].lower()}_name>;\t// {register['description']}\n'

        # Generate static array registers
        arrays = ''
        for register in registers:
            if register['length']:
                arrays += f'static inline {register['name']}_t {register['name']};\t// {register['description']}\n'

        # Generate register packs
        packs = ''
        for register in registers:
            if not register['length']:
                packs += f'\t\ttemplate<typename... T> using {register['name']}Pack = RegisterPack<{register['name']}, T...>;\t// {register['description']} pack\n'

        # Generate registers
        registers_str = ''
        for register in registers:

            # If empty fields or width of register = width of field
            if register['length'] == 0:
                if len(register['fields']) == 0 or register['width'] == register['fields'][0]['width']:
                    registers_str += f'using {register['name']} = RegisterBase<{register['name'].lower()}_address, {register['width']}, {register['length']}, {register['access']}, Target, STM32F4xxx, {register['name'].lower()}_name>;\t// {register['description']}\n'

                else:
                    # Generate fields name
                    names = generate_names('', register['fields'])

                    # Generate fields
                    fields = ''
                    for field in register['fields']:
                        fields += f'using {field['name']} = {register['name']}_{field['name']}<{register['name']}, {field['offset']}, {field['width']}, {field['access']}, Target, STM32F4xxx, {field['name'].lower()}_name>;\t// {field['description']}\n'

                    registers_str += (
                        f'// {register['description']}\n'
                        f'class {register['name']}: public RegisterBase<{register['name'].lower()}_address, {register['width']}, {register['length']}, {register['access']}, Target, STM32F4xxx, {register['name'].lower()}_name>\n'
                        f'{{\n'
                        f'{names}\n'
                        f'public:\n'
                        f'{fields}\n'
                        f'}};\n'
                    )

        if array_types != '':
            register_names += '\n'

        text = (
            f'#pragma once\n\n'
            f'#include "{config['base']['common']}/RegisterBase.h"\n'
            f'#include "{config['base']['common']}/RegisterPack.h"\n'
            f'#include "{config['base']['common']}/RegisterArray.h"\n'
            f'#include "{config['base']['common']}/FieldBase.h"\n'
            f'#include "{config['base']['common']}/ValueBase.h"\n'
            f'#include "{config['base']['fields']}/{peripheral['name']}.h"\n'
            f'#include "{config['base']['root']}/{config['targets']}"\n'
            f'namespace {namespace}::{peripheral['name'].lower()}\n'
            f'{{\n'
            f'// {peripheral['description']}\n'
            f'template<class Target, {addresses[:-2]}>\n'
            f'class {peripheral['name']}Base\n'
            f'{{\n'
            f'{register_names}\n'
            f'{array_types}'
            f'public:\n'
            f'{registers_str}\n'
            f'{arrays}'
            f'\n// clang-format off\n'
            f'{packs[:-1]}\n'
            f'// clang-format on\n'
            f'}};\n'
            f'}}\n'
        )

        path = Path('.').cwd()/f'{config['root']['base']}/{peripheral['name']}.h'
        with open(path, 'w') as header:
            header.write(text)

    path = Path('.').cwd() / f'{config['root']['base']}/*.h'
    run_clang_format(path)


def create_field_files(namespace: str, peripherals: list, config: dict):
    Path(config['root']['fields']).mkdir(parents=True, exist_ok=True)
    for peripheral in peripherals:
        # Generate fields structs
        fields = ''
        for register in peripheral['registers']:
            for field in register['fields']:
                name = f'{register['name']}_{field['name']}'

                # Generate values names
                names = generate_names('', field['values'])

                # Generate values structs
                values = ''
                for value in field['values']:
                    values += f'using {value['name']} = ValueBase<{name}, {value['value']}, Target, Family, {value['name'].lower()}_name>;\t// {value['description']}\n'

                if len(field['values']):
                    fields += (
                        f'// {field['description']}\n'
                        f'template<class Register, size_t offset, size_t width, class Access, class Target, class Family, const char* name>\n'
                        f'class {name}: public FieldBase<Register, offset, width, Access, Target, Family, name>\n'
                        f'{{\n'
                        f'{names}\n'
                        f'public:\n'
                        f'{values}\n'
                        f'}};\n'
                    )
                else:
                    fields += (
                        f'// {field['description']}\n'
                        f'template<class Register, size_t offset, size_t width, class Access, class Target, class Family, const char* name>\n'
                        f'class {name}: public FieldBase<Register, offset, width, Access, Target, Family, name>\n'
                        f'{{\n'
                        f'}};\n'
                    )



        text = (
            f'#pragma once\n\n'
            f'#include "{config['fields']['common']}/FieldBase.h"\n'
            f'#include "{config['fields']['common']}/ValueBase.h"\n'
            f'namespace {namespace}::{peripheral['name'].lower()}\n'
            f'{{\n'
            f'{fields}\n'
            f'}}\n'
        )

        path = Path('.').cwd() / f'{config['root']['fields']}/{peripheral['name']}.h'
        with open(path, 'w') as header:
            header.write(text)

    path = Path('.').cwd() / f'{config['root']['fields']}/*.h'
    run_clang_format(path)


def create_driver_files(namespace: str, peripherals: list, config: dict):

    # Create dir for files
    Path(config['root']['drivers']).mkdir(parents=True, exist_ok=True)

    for peripheral in peripherals:
        text = (
            f'#pragma once\n\n'
            f'namespace {namespace}::{peripheral['name'].lower()}\n'
            f'{{\n'
            f'template<class {peripheral['name']}>'
            f'\tclass Driver\n'
            f'{{\n'
            f'}};\n'
            f'}}\n'
        )

        path = Path('.').cwd() / f'{config['root']['drivers']}/{peripheral['name']}.h'
        with open(path, 'w') as header:
            header.write(text)

    path = Path('.').cwd() / f'{config['root']['drivers']}/*.h'
    run_clang_format(path)


def create_peripheral_files(namespace: str, peripherals: list, config: dict):

    Path(config['root']['peripherals']).mkdir(parents=True, exist_ok=True)

    headers = f'#pragma once\n\n'
    for peripheral in peripherals:

        registers = ''
        name = peripheral['name']

        if peripheral.get('address'):
            registers += f'\tusing Registers = {name}Base<Target, {name}_ADDRESS>;\n'
        else:
            for element in peripheral['derived']:
                current_name = element['name']
                registers += f'\tusing Registers{current_name} = {name}Base<Target, {current_name}_ADDRESS>;\n'

        peripheral_list = ''
        common_name = peripheral['name']
        driver_namespace = f'{common_name.lower()}'

        if peripheral.get('address'):
            peripheral_list += f'\tstruct {common_name}: {driver_namespace}::Registers {{ using Driver = {driver_namespace}::Driver<{common_name.lower()}::Registers>; }};\n'

        else:
            for element in peripheral['derived']:
                peripheral_list += f'\tstruct {element['name']}: {driver_namespace}::Registers{element['name']} {{ using Driver = {driver_namespace}::Driver<{driver_namespace}::Registers{element['name']}>; }};\n'

        text = str(
            f'#pragma once\n\n'
            f'#include "{config['peripherals']['root']}/{config['address']}"\n'
            f'#include "{config['peripherals']['root']}/{config['targets']}"\n'
            f'#include "{config['peripherals']['base']}/{name}.h"\n'
            f'#include "{config['peripherals']['drivers']}/{name}.h"\n\n'
            f'namespace {namespace}::{name.lower()}\n'
            f'{{\n'
            f'{registers[:-1]}\n'
            f'}}\n\n'
            f'namespace {namespace}\n'
            f'{{\n'
            f'\t// clang-format off\n'
            f'{peripheral_list[:-1]}\n'
            f'\t// clang-format on\n'
            f'}}\n'
        )

        path = Path('.').cwd() / f'{config['root']['peripherals']}/{peripheral['name']}.h'
        with open(path, 'w') as header:
            header.write(text)
        headers += f'#include "{config['root']['peripherals']}/{name}.h"\n'

    path = Path('.').cwd() / f'{config['final']}'
    with open(path, 'w') as common:
        common.write(headers)

    run_clang_format(path)


def create_addresses_file(peripherals: list, config: dict):
    # Generate storage structs
    structs = ''
    for peripheral in peripherals:
        registers = ''
        for register in peripheral['registers']:
            width = 'uint8_t' if register['width'] == 8 else 'uint16_t' if register['width'] == 16 else 'uint32_t'
            registers += f'static inline {width} {register['name']}[{register['length']}] = {{0}};\n' if register['length'] else f'static inline {width} {register['name']} = 0;\n'

        if peripheral.get('address'):
            structs += (
                f'struct {peripheral['name']}\n'
                f'{{\n'
                f'{registers[:-1]}\n'
                f'}};\n\n'
            )
        else:
            for elements in peripheral['derived']:
                structs += (
                    f'struct {elements['name']}\n'
                    f'{{\n'
                    f'{registers[:-1]}\n'
                    f'}};\n\n'
                )

    # Generate storage address list
    storage_address_list = ''
    for peripheral in peripherals:
        names = ''
        if peripheral.get('address'):
            for register in peripheral['registers']:
                names += f'{peripheral['name']}::{register['name']}, ' if register['length'] else f'&{peripheral['name']}::{register['name']}, '
            storage_address_list += f'#define {peripheral['name']}_ADDRESS {names[:-2]}\n'

        else:
            for element in peripheral['derived']:
                names = ''
                for register in peripheral['registers']:
                    names += f'{element['name']}::{register['name']}, ' if register['length'] else f'&{element['name']}::{register['name']}, '
                storage_address_list += f'#define {element['name']}_ADDRESS {names[:-2]}\n'

    # Generate default address list
    address_list = ''
    for peripheral in peripherals:
        if peripheral.get('address'):
            address_list += f'#define {peripheral['name']}_ADDRESS {peripheral['address']}\n'
        else:
            for element in peripheral['derived']:
                address_list += f'#define {element['name']}_ADDRESS {element['address']}\n'

    text = str(
        f'#pragma once\n\n'
        f'#include <cstdint>\n\n'
        f'#ifdef SIMULATION\n'
        f'{structs[:-2]}\n'
        f'#endif\n\n'
        f'#ifdef SIMULATION\n'
        f'{storage_address_list}\n'
        f'#else\n'
        f'{address_list}\n'
        f'#endif\n'
    )

    path = Path('.').cwd() / f'{config['address']}'
    with open(path, 'w') as header:
        header.write(text)

    run_clang_format(path)


def get_peripherals(tree: Et.Element, includes: list):

    peripherals = list()
    for i, branch in enumerate(tree):

        derived = None if tree[i].attrib == {} else tree[i].attrib['derivedFrom'].upper()
        name = tree[i].find('name').text.upper()
        addresses = {'name': name, 'address': f'0x{tree[i].find('baseAddress').text.upper()[2:]}'}
        group = None
        description = None
        registers = []

        if derived:
            i = get_derived_index(derived, peripherals)
            peripheral = peripherals[i]
            peripheral['derived'].append(addresses)
            continue
        else:
            group = tree[i].find('groupName').text.upper()
            temp = tree[i].find('description').text.capitalize()
            description = process_description(temp)
            registers = process_registers(tree[i].find('registers'))

        peripherals.append({'group': group, 'derived': [addresses], 'description': description, 'registers': registers})

    temp = []
    if includes:
        for include in includes:
            for peripheral in peripherals:
                if include == peripheral['group']:
                    temp.append(peripheral)
                    break
        peripherals = temp.copy()
        temp.clear()

    for peripheral in peripherals:
        if len(peripheral['derived']) == 1:
            address = peripheral['derived'][0]['address']
            temp.append({'name': peripheral['group'], 'description': peripheral['description'], 'address': address, 'registers': peripheral['registers']})
        else:
            derived = sorted(peripheral['derived'], key=lambda item: item['address'])
            temp.append({'name': peripheral['group'],'description': peripheral['description'],'derived': derived,'registers': peripheral['registers']})

    return temp


def get_relative_path(source: Path, target: Path):
    return str(source.relative_to(target, walk_up=True)).replace('\\', '/')


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--include', '-i', nargs='+', help='list of peripherals to include')
    parser.add_argument('--base', '-b', help='generate base files', nargs='?', const='')
    parser.add_argument('--fields', '-f', help='generate field files', nargs='?', const='')
    parser.add_argument('--drivers', '-d', help='generate driver files', nargs='?', const='')
    parser.add_argument('--source', '-s', help='source file', nargs='?', const='')
    parser.add_argument('--json', '-j', help='svd to json', nargs='?', const='')

    args = parser.parse_args()
    includes = args.include
    base = True if args.base == '' else False
    fields = True if args.fields == '' else False
    drivers = True if args.drivers == '' else False
    source = Path(args.source)
    need_json = True if args.json == '' else False

    current = Path('.')
    common_namespace = 'mcu'
    peripherals = []

    root_path = current.cwd()
    base_path = root_path / 'Base'
    common_path = root_path / 'Common'
    drivers_path = root_path / 'Drivers'
    peripherals_path = root_path / 'Registers'
    fields_path = root_path / 'Fields'

    if source.suffix == '.svd':
        tree = Et.parse(source.name)
        root = tree.getroot()
        peripherals = get_peripherals(root.find('peripherals'), includes)

        if need_json:
            with open(f'{source.stem}.json', 'w') as output:
                json.dump(peripherals, output, indent=4)

    elif source.suffix == '.json':
        with open(source, 'r') as file:
            peripherals = json.load(file)

    config = {
        'base': {
            'root': get_relative_path(root_path, base_path),
            'common': get_relative_path(common_path, base_path),
            'drivers': get_relative_path(drivers_path, base_path) ,
            'fields': get_relative_path(fields_path, base_path),
            'peripherals': get_relative_path(peripherals_path, base_path),
        },
        'fields': {
            'root': get_relative_path(root_path, fields_path),
            'base': get_relative_path(base_path, fields_path),
            'common': get_relative_path(common_path, fields_path),
            'drivers': get_relative_path(drivers_path, fields_path),
            'peripherals': get_relative_path(peripherals_path, fields_path),
        },
        'peripherals': {
            'root': get_relative_path(root_path, peripherals_path),
            'base': get_relative_path(base_path, peripherals_path),
            'common': get_relative_path(common_path, peripherals_path),
            'drivers': get_relative_path(drivers_path, peripherals_path),
            'fields': get_relative_path(fields_path , peripherals_path),
        },
        'root': {
            'base': get_relative_path(base_path, root_path),
            'common': get_relative_path(common_path, root_path),
            'drivers': get_relative_path(drivers_path, root_path),
            'fields': get_relative_path(fields_path, root_path),
            'peripherals': get_relative_path(peripherals_path, root_path),
        },
        'address': 'addresses.h',
        'final': 'peripherals.h',
        'targets': 'targets.h'
    }

    if base:
        create_base_files(common_namespace, peripherals, config)

    if fields:
        create_field_files(common_namespace, peripherals, config)

    if drivers:
        create_driver_files(common_namespace, peripherals, config)

    create_peripheral_files(common_namespace, peripherals, config)
    create_addresses_file(peripherals, config)