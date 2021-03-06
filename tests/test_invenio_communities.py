# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2016 CERN.
#
# Invenio is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Invenio is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Invenio; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.
#
# In applying this license, CERN does not
# waive the privileges and immunities granted to it by virtue of its status
# as an Intergovernmental Organization or submit itself to any jurisdiction.


"""Module tests."""

from __future__ import absolute_import, print_function

from datetime import datetime, timedelta

import pytest
from flask import Flask
from flask_cli import FlaskCLI
from invenio_accounts.testutils import create_test_user
from invenio_db import db
from invenio_oaiserver.models import OAISet
from invenio_records.api import Record

from invenio_communities import InvenioCommunities
from invenio_communities.errors import InclusionRequestExistsError, \
    InclusionRequestMissingError, InclusionRequestObsoleteError
from invenio_communities.models import Community, FeaturedCommunity, \
    InclusionRequest


def test_version():
    """Test version import."""
    from invenio_communities import __version__
    assert __version__


def test_init():
    """Test extension initialization."""
    app = Flask('testapp')
    FlaskCLI(app)
    ext = InvenioCommunities(app)
    assert 'invenio-communities' in app.extensions

    app = Flask('testapp')
    FlaskCLI(app)
    ext = InvenioCommunities()
    assert 'invenio-communities' not in app.extensions
    ext.init_app(app)
    assert 'invenio-communities' in app.extensions


def test_model_init(app):
    """Test basic model initialization and actions."""
    with app.app_context():
        # Init the User and the Community
        user1 = create_test_user()
        comm1 = Community(id='comm1', id_user=user1.id)
        db.session.add(comm1)
        db.session.commit()
        communities_key = app.config["COMMUNITIES_RECORD_KEY"]
        # Create a record and accept it into the community by creating an
        # InclusionRequest and then calling the accept action
        rec1 = Record.create({'title': 'Foobar'})
        InclusionRequest.create(community=comm1, record=rec1)
        assert InclusionRequest.query.count() == 1
        comm1.accept_record(rec1)
        assert 'comm1' in rec1[communities_key]
        assert InclusionRequest.query.count() == 0

        # Likewise, reject a record from the community
        rec2 = Record.create({'title': 'Bazbar'})
        InclusionRequest.create(community=comm1, record=rec2)
        assert InclusionRequest.query.count() == 1
        comm1.reject_record(rec2)
        assert communities_key not in rec2  # dict key should not be created
        assert InclusionRequest.query.count() == 0

        # Add record to another community
        comm2 = Community(id='comm2', id_user=user1.id)
        db.session.add(comm2)
        db.session.commit()
        InclusionRequest.create(community=comm2, record=rec1)
        comm2.accept_record(rec1)
        assert communities_key in rec1
        assert len(rec1[communities_key]) == 2
        assert comm1.id in rec1[communities_key]
        assert comm2.id in rec1[communities_key]

        # Accept/reject a record to/from a community without inclusion request
        rec3 = Record.create({'title': 'Spam'})
        pytest.raises(InclusionRequestMissingError, comm1.accept_record, rec3)
        pytest.raises(InclusionRequestMissingError, comm1.reject_record, rec3)

        # Create two inclusion requests
        comm3 = Community(id='comm3', id_user=user1.id)
        db.session.add(comm3)
        db.session.commit()
        InclusionRequest.create(community=comm3, record=rec1)
        pytest.raises(InclusionRequestExistsError, InclusionRequest.create,
                      community=comm3, record=rec1)

        # Try to accept a record to a community twice (should raise)
        # (comm1 is already in rec1)
        pytest.raises(InclusionRequestObsoleteError, InclusionRequest.create,
                      community=comm1, record=rec1)


def test_model_featured_community(app):
    """Test the featured community model and actions."""
    with app.app_context():
        # Create a user and two communities
        t1 = datetime.now()
        user1 = create_test_user()
        comm1 = Community(id='comm1', id_user=user1.id)
        comm2 = Community(id='comm2', id_user=user1.id)
        db.session.add(comm1)
        db.session.add(comm2)
        db.session.commit()

        # Create two community featurings starting at different times
        fc1 = FeaturedCommunity(id_community=comm1.id,
                                start_date=t1 + timedelta(days=1))
        fc2 = FeaturedCommunity(id_community=comm2.id,
                                start_date=t1 + timedelta(days=3))
        db.session.add(fc1)
        db.session.add(fc2)
        # Check the featured community at three different points in time
        assert FeaturedCommunity.get_featured_or_none(start_date=t1) is None
        assert FeaturedCommunity.get_featured_or_none(
            start_date=t1 + timedelta(days=2)) is comm1
        assert FeaturedCommunity.get_featured_or_none(
            start_date=t1 + timedelta(days=4)) is comm2


def test_oaipmh_sets(app):
    """Test the OAI-PMH Sets creation."""
    with app.app_context():
        # Create a user
        user1 = create_test_user()
        comm1 = Community(id='comm1',
                          id_user=user1.id,
                          title='Title1',
                          description='Description1')
        db.session.add(comm1)
        db.session.commit()
        assert OAISet.query.count() == 1
        oai_set1 = OAISet.query.first()
        assert oai_set1.spec == 'user-comm1'
        assert oai_set1.name == 'Title1'
        assert oai_set1.description == 'Description1'
        assert oai_set1.search_pattern == 'community:"comm1"'

        # Delete the community and make sure the set is also deleted
        db.session.delete(comm1)
        db.session.commit()
        assert Community.query.count() == 0
        assert OAISet.query.count() == 0
