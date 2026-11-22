"""Fast, solver-free tests for inp2rad material conversion and mapping."""
import contextlib
import io
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'inp2rad'))
import inp2rad  # noqa: E402


def convert(lines):
    """Run convert_materials while capturing its warnings."""
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = inp2rad.convert_materials(list(lines), 0)
    return result, stream.getvalue()


class MaterialDispatchTests(unittest.TestCase):

    def test_required_keys_are_subset_not_exact_set(self):
        props = {
            'material_id': 1, 'rho': 7.8e-9, 'emodulus': 210000.0,
            'poissrat': 0.3, 'unsupported_extra_key': 42
        }
        self.assertTrue(inp2rad.check_if_elast(props))
        self.assertTrue(inp2rad.check_if_mass({
            'material_id': 2, 'masselement': 'yes', 'mass': 1.0, 'extra': 'x'
        }))

    def test_missing_required_key_still_fails(self):
        self.assertFalse(inp2rad.check_if_elast({
            'material_id': 1, 'emodulus': 210000.0, 'poissrat': 0.3
        }))

    def test_specific_law_does_not_also_match_isotropic(self):
        props = {
            'material_id': 1, 'rho': 7.8e-9, 'emodulus': 210000.0,
            'poissrat': 0.3, 'plastic_data': {'rate_sets': []}
        }
        self.assertTrue(inp2rad.check_if_plast(props))
        self.assertFalse(inp2rad.check_if_elast(props))

    def test_material_name_with_equals_sign(self):
        (materials, _extra, _fct, _n), _ = convert([
            '*MATERIAL, NAME=STEEL=A36',
            '*DENSITY', '7.8e-9',
            '*ELASTIC', '210000, 0.3',
        ])
        self.assertIn('STEEL=A36', materials)
        self.assertEqual(materials['STEEL=A36']['rho'], 7.8e-9)

    def test_name_after_other_material_parameters(self):
        (materials, _extra, _fct, _n), output = convert([
            '*MATERIAL, TYPE=ISOTROPIC, NAME=STEEL',
            '*DENSITY', '7.8e-9',
            '*ELASTIC', '210000, 0.3',
        ])
        self.assertIn('STEEL', materials)
        self.assertEqual(materials['STEEL']['emodulus'], 210000.0)
        self.assertNotIn('missing NAME=', output)

    def test_missing_density_warns(self):
        (_materials, _extra, _fct, _n), output = convert([
            '*MATERIAL, NAME=NO_RHO',
            '*ELASTIC', '210000, 0.3',
        ])
        self.assertIn('no *DENSITY', output)
        self.assertIn('NO_RHO', output)


class PlasticTests(unittest.TestCase):

    def _deck(self, header='*PLASTIC', rows=None):
        return [
            '*MATERIAL, NAME=STEEL',
            '*DENSITY', '7.8e-9',
            '*ELASTIC', '210000, 0.3',
            header,
        ] + (rows if rows is not None else ['200, 0.0', '300, 0.1'])

    def test_plain_plastic_is_converted(self):
        (materials, _extra, _fct, _n), output = convert(self._deck())
        self.assertNotIn('WARNING', output)
        sets = materials['STEEL']['plastic_data']['rate_sets']
        self.assertEqual(sets[0]['rate'], 1.0)
        self.assertEqual(sets[0]['xy_data'], [(0.0, 200.0), (0.1, 300.0)])

    def test_hardening_models_are_skipped_with_warning(self):
        for hardening in ('JOHNSON COOK', 'KINEMATIC', 'COMBINED'):
            with self.subTest(hardening=hardening):
                (materials, _extra, _fct, _n), output = convert(
                    self._deck(f'*PLASTIC, HARDENING={hardening}')
                )
                self.assertNotIn('plastic_data', materials['STEEL'])
                self.assertIn(hardening, output)
                self.assertIn('WARNING', output)

    def test_temperature_dependent_plastic_is_skipped(self):
        (materials, _extra, _fct, _n), output = convert(
            self._deck('*PLASTIC, TEMPERATURE DEPENDENT')
        )
        self.assertNotIn('plastic_data', materials['STEEL'])
        self.assertIn('TEMPERATURE DEPENDENT', output)

    def test_extra_temperature_column_is_skipped(self):
        (materials, _extra, _fct, _n), output = convert(
            self._deck(rows=['200, 0.0, 20.', '300, 0.1, 100.'])
        )
        self.assertNotIn('plastic_data', materials['STEEL'])
        self.assertIn('temperature/field column', output)

    def test_negative_stress_and_strain_are_made_positive(self):
        (materials, _extra, _fct, _n), _ = convert(
            self._deck(rows=['-200, -0.0', '-300, -0.1'])
        )
        self.assertEqual(
            materials['STEEL']['plastic_data']['rate_sets'][0]['xy_data'],
            [(0.0, 200.0), (0.1, 300.0)]
        )

    def test_law36_fscale_is_not_zero(self):
        plastic_data = {'rate_sets': [
            {'fct_id': 10, 'rate': 0.001, 'fscale': 1.0,
             'xy_data': [(0.0, 200.0), (0.1, 300.0)]},
            {'fct_id': 11, 'rate': 1.0, 'fscale': 1.2,
             'xy_data': [(0.0, 220.0), (0.1, 330.0)]},
        ]}
        stream = io.StringIO()
        inp2rad.write_plastic_material(1, 'STEEL', 7.8e-9, 210000.0, 0.3,
                                       plastic_data, stream)
        text = stream.getvalue()
        self.assertIn('/MAT/PLAS_TAB/1', text)
        fscale_line = text.split('Fscale_1')[1].split('\n')[1]
        self.assertEqual(fscale_line.split()[0], '1')  # default Fscale is 1, not 0
        self.assertIn('1.2', fscale_line)  # user supplied Fscale is honoured
        self.assertIn('/FUNCT/10', text)
        self.assertIn('/FUNCT/11', text)


class OrthotropicTests(unittest.TestCase):

    CONSTANTS = '200000, 15000, 15000, 0.3, 0.3, 0.25, 5000, 5000, 3000'

    def test_full_engineering_constants_are_mapped(self):
        (materials, _extra, _fct, _n), output = convert([
            '*MATERIAL, NAME=COMPOSITE',
            '*DENSITY', '1.6e-9',
            '*ELASTIC, TYPE=ENGINEERING CONSTANTS', self.CONSTANTS,
        ])
        constants = materials['COMPOSITE']['orthotropic_constants']
        self.assertEqual(constants['e1'], 200000.0)
        self.assertEqual(constants['g23'], 3000.0)
        self.assertTrue(inp2rad.check_if_ortho(materials['COMPOSITE']))
        self.assertFalse(inp2rad.check_if_elast(materials['COMPOSITE']))
        self.assertIn('orientation', output)

        stream = io.StringIO()
        inp2rad.write_orthotropic_material(1, 'COMPOSITE', 1.6e-9,
                                           constants, stream)
        text = stream.getvalue()
        self.assertIn('/MAT/LAW93/1', text)
        self.assertIn('200000', text)
        self.assertIn('3000', text)
        # LAW93 cards list the yield-parameter and Hill ratio lines even when
        # Nrate=0; SigY=1E30 keeps the material elastic.
        self.assertIn('SigY', text)
        self.assertIn('e+30', text)
        self.assertIn('R11', text)
        self.assertIn('R33', text)
        self.assertEqual(text.count('R11'), 1)

    def test_partial_constants_fall_back_with_warning(self):
        (materials, _extra, _fct, _n), output = convert([
            '*MATERIAL, NAME=PARTIAL',
            '*DENSITY', '1.6e-9',
            '*ELASTIC, TYPE=ENGINEERING CONSTANTS', '200000, 15000, 15000, 0.3',
        ])
        self.assertIn('Falling back', output)
        self.assertEqual(materials['PARTIAL']['emodulus'], 200000.0)
        self.assertEqual(materials['PARTIAL']['poissrat'], 0.3)


class TemperatureAndD1Tests(unittest.TestCase):

    def test_temperature_columns_are_reported(self):
        (materials, _extra, _fct, _n), output = convert([
            '*MATERIAL, NAME=TEMP',
            '*DENSITY', '7.8e-9, 20.',
            '*ELASTIC', '210000, 0.3, 20.', '200000, 0.31, 100.',
        ])
        self.assertIn('temperature dependency', output)
        self.assertEqual(materials['TEMP']['density_temperature_data'], [(20.0, 7.8e-9)])
        self.assertEqual(len(materials['TEMP']['elastic_temperature_data']), 2)

        stream = io.StringIO()
        inp2rad.write_elastic_material(
            1, 'TEMP', 7.8e-9, 210000, 0.3, stream,
            materials['TEMP']['density_temperature_data'],
            materials['TEMP']['elastic_temperature_data']
        )
        self.assertIn('temperature dependent density/elastic data was ignored',
                      stream.getvalue())

    def test_d1_compressibility_warnings(self):
        _result, output = convert([
            '*MATERIAL, NAME=NH',
            '*DENSITY', '1e-9',
            '*HYPERELASTIC, NEO HOOKE', '2.0, 0.0001',
            '*MATERIAL, NAME=MR',
            '*DENSITY', '1e-9',
            '*HYPERELASTIC, MOONEY-RIVLIN', '1.0, 0.5, 0.0002',
        ])
        self.assertIn('D1 compressibility', output)
        self.assertEqual(output.count('D1 compressibility'), 2)


class OgdenTests(unittest.TestCase):

    def test_multi_term_ogden_is_written(self):
        (materials, _extra, _fct, _n), _ = convert([
            '*MATERIAL, NAME=OGDEN2',
            '*DENSITY', '1e-9',
            '*HYPERELASTIC, OGDEN, N=2', '1.0, 2.0, 0.001, 0.5, 3.0, 0.002',
        ])
        self.assertEqual(len(materials['OGDEN2']['ogden_terms']), 2)
        self.assertTrue(inp2rad.check_if_ogden(materials['OGDEN2']))
        stream = io.StringIO()
        inp2rad.write_ogden_material(1, 'OGDEN2', 1e-9,
                                     materials['OGDEN2']['ogden_terms'], stream)
        text = stream.getvalue()
        self.assertIn('/MAT/LAW82/1', text)
        self.assertIn('         2', text)
        self.assertIn('0.002', text)


class DamageEvolutionTests(unittest.TestCase):

    def test_damage_evolution_table_is_written_as_function(self):
        (materials, extra, _fct, _n), output = convert([
            '*MATERIAL, NAME=DUCTILE',
            '*DENSITY', '7.8e-9',
            '*ELASTIC', '210000, 0.3',
            '*DAMAGE EVOLUTION, TYPE=DUCTILE', '0.0, 0.0', '0.5, 1.0',
        ])
        data = extra['DUCTILE']['damage_evolution_data']
        self.assertEqual(data['type'], 'DUCTILE')
        self.assertEqual(data['xy_data'], [(0.0, 0.0), (0.5, 1.0)])
        self.assertTrue(inp2rad.check_if_damage_evolution(extra['DUCTILE']))
        self.assertIn('map it to a Radioss failure model manually', output)

        stream = io.StringIO()
        inp2rad.write_damage_evolution(materials['DUCTILE']['material_id'],
                                       data, 'DUCTILE', stream)
        self.assertIn(f"/FUNCT/{data['fct_id']}", stream.getvalue())


class MassTests(unittest.TestCase):

    def test_mass_without_elset_builds_node_group(self):
        (materials, _extra, _fct, _n), output = convert([
            '*MASS', '101, 5.0', '102, 3.0',
        ])
        name = next(iter(materials))
        self.assertEqual(materials[name]['mass_nodes'], ['101', '102'])
        self.assertEqual(materials[name]['mass'], 8.0)
        self.assertIn('GRNOD', output)

        stream = io.StringIO()
        inp2rad.write_admas(name, {}, 8.0, stream,
                            materials[name]['mass_nodes'],
                            materials[name]['mass_grnid'])
        grnid = materials[name]['mass_grnid']
        self.assertIn(f'/GRNOD/NODE/{grnid}', stream.getvalue())
        self.assertIn(f'/ADMAS/0/{grnid}', stream.getvalue())

    def test_two_mass_cards_get_unique_group_ids(self):
        (materials, _extra, _fct, _n), _output = convert([
            '*MASS', '101, 5.0',
            '*MASS', '102, 3.0',
        ])
        grnids = [props['mass_grnid'] for props in materials.values()]
        self.assertEqual(len(grnids), 2)
        self.assertEqual(len(set(grnids)), 2)

    def test_unresolved_mass_group_is_skipped_with_warning(self):
        stream = io.StringIO()
        text_out = io.StringIO()
        with contextlib.redirect_stdout(text_out):
            inp2rad.write_admas('MISSING', {}, 1.0, stream)
        self.assertNotIn('/ADMAS', stream.getvalue())
        self.assertIn('could not be resolved', text_out.getvalue())


class EndToEndMassTests(unittest.TestCase):
    """Regression tests for the full start()/write_output() path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_or_gui = inp2rad.or_gui
        self.old_run_timer = inp2rad.run_timer
        inp2rad.or_gui = True   # avoids the interactive 'Press Enter' prompt
        inp2rad.run_timer = False

    def tearDown(self):
        inp2rad.or_gui = self.old_or_gui
        inp2rad.run_timer = self.old_run_timer
        self.tmp.cleanup()

    def _convert_deck(self, name, deck):
        input_path = os.path.join(self.tmp.name, name + '.inp')
        with open(input_path, 'w') as handle:
            handle.write(deck)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            success = inp2rad.start(input_path)
        self.assertTrue(success, stream.getvalue())
        rad_path = os.path.join(self.tmp.name, name + '_0000.rad')
        self.assertTrue(os.path.exists(rad_path))
        with open(rad_path) as handle:
            return handle.read()

    def test_start_succeeds_with_one_mass_card(self):
        text = self._convert_deck('one_mass', '*MASS\n101, 5.0\n')
        grnids = re.findall(r'/GRNOD/NODE/(\d+)', text)
        admas_ids = re.findall(r'/ADMAS/0/(\d+)', text)
        self.assertEqual(len(grnids), 1)
        self.assertEqual(grnids, admas_ids)

    def test_start_succeeds_with_two_mass_cards_and_unique_group_ids(self):
        text = self._convert_deck(
            'two_masses', '*MASS\n101, 5.0\n*MASS\n102, 3.0\n'
        )
        grnids = re.findall(r'/GRNOD/NODE/(\d+)', text)
        admas_ids = re.findall(r'/ADMAS/0/(\d+)', text)
        self.assertEqual(len(grnids), 2)
        self.assertEqual(len(set(grnids)), 2)
        self.assertEqual(grnids, admas_ids)


if __name__ == '__main__':
    unittest.main()
