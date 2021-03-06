# Copyright 2017  Lars Wirzenius
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# =*= License: GPL-3+ =*=


import logging
import sys

import cliapp
import jinja2
import yaml

import vmdb


class Vmdb2(cliapp.Application):

    def add_settings(self):
        self.settings.string(
            ['image'],
            'create image file FILE',
            metavar='FILE')

        self.settings.boolean(
            ['verbose', 'v'],
            'verbose output')

    def setup(self):
        self.step_runners = vmdb.StepRunnerList()

    def process_args(self, args):
        if len(args) != 1:
            sys.exit("No image specification was given on the command line.")

        vmdb.set_verbose_progress(self.settings['verbose'])

        spec = self.load_spec_file(args[0])

        steps = spec['steps']
        # Check that we have step runners for each step
        for step in steps:
            self.step_runners.find(step)

        state = vmdb.State()
        steps_taken, core_meltdown = self.run_steps(steps, state)
        if core_meltdown:
            vmdb.progress('Something went wrong, cleaning up!')
        else:
            vmdb.progress('All went fine, cleaning up.')
        self.run_teardowns(steps_taken, state)

        if core_meltdown:
            logging.error('An error occurred, exiting with non-zero exit code')
            sys.exit(1)

    def load_spec_file(self, filename):
        vmdb.progress('Load spec file {}'.format(filename))
        with open(filename) as f:
            return yaml.safe_load(f)

    def run_steps(self, steps, state):
        return self.run_steps_helper(
            steps, state, 'Running step: %r', 'run', False)

    def run_teardowns(self, steps, state):
        return self.run_steps_helper(
            list(reversed(steps)), state, 'Running teardown: %r', 'teardown', True)

    def run_steps_helper(self, steps, state, msg, method_name, keep_going):
        core_meltdown = False
        steps_taken = []

        for step in steps:
            try:
                logging.info(msg, step)
                steps_taken.append(step)
                expanded_step = self.expand_step_spec(step, state)
                runner = self.step_runners.find(step)
                if runner.skip(step, self.settings, state):
                    logging.info('Skipping as requested')
                else:
                    method = getattr(runner, method_name)
                    method(expanded_step, self.settings, state)
            except BaseException as e:
                vmdb.error(str(e))
                core_meltdown = True
                if not keep_going:
                    break

        return steps_taken, core_meltdown

    def format_step(self, runner, step):
        return str(step)

    def expand_step_spec(self, step, state):
        expanded = {}
        for key in step:
            expanded[key] = self.expand_jinja2(step[key], state)
        return expanded

    def expand_jinja2(self, value, state):
        template = jinja2.Template(value)
        vars = self.create_template_vars(state)
        return template.render(**vars)

    def create_template_vars(self, state):
        vars = dict()
        for key in self.settings:
            vars[key] = self.settings[key]
        vars.update(state.as_dict())
        return vars
