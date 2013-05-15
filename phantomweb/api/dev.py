import base64
import json
import logging

from django.contrib.auth import authenticate, login
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed, HttpResponseNotFound, HttpResponseServerError
from django.views.decorators.http import require_http_methods

from phantomweb.util import get_user_object
from phantomweb.workload import phantom_get_sites, get_all_launch_configurations, get_launch_configuration, delete_launch_configuration

log = logging.getLogger('phantomweb.api.dev')


def basic_http_auth(f):
    def wrap(request, *args, **kwargs):
        if request.user:
            if request.user.is_authenticated():
                # Already logged in, just return the result of the view
                return f(request, *args, **kwargs)

        if request.META.get('HTTP_AUTHORIZATION', False):
            authtype, auth = request.META['HTTP_AUTHORIZATION'].split(' ')
            auth = base64.b64decode(auth)
            username, password = auth.split(':')

            user = authenticate(username=username, password=password)
            if user is not None:
                if user.is_active:
                    login(request, user)
                    return f(request, *args, **kwargs)
                else:
                    r = HttpResponse("Your account has been disabled", status=401, mimetype='application/javascript')
                    r['WWW-Authenticate'] = 'Basic realm="api"'
                    return r
            else:
                r = HttpResponse("Your username and password were incorrect", status=401, mimetype='application/javascript')
                r['WWW-Authenticate'] = 'Basic realm="api"'
                return r
        else:
            r = HttpResponse("Auth Required", status=401, mimetype='application/javascript')
            r['WWW-Authenticate'] = 'Basic realm="api"'
            return r

    return wrap


def has_all_required_params(params, content):
    for param in params:
        if param not in content:
            return False

    return True


@basic_http_auth
@require_http_methods(["GET"])
def sites(request):
    user_obj = get_user_object(request.user.username)

    all_sites = phantom_get_sites(request.GET, user_obj)
    response_list = []
    for site in all_sites:
        site_name = str(site)
        site_dict = {
            "id": site_name,
            "credentials": "/api/dev/credentials/%s" % site_name,
            "uri": "/api/dev/sites/%s" % site_name
        }
        response_list.append(site_dict)
    h = HttpResponse(json.dumps(response_list), mimetype='application/javascript')
    return h


@basic_http_auth
@require_http_methods(["GET"])
def site_resource(request, site):
    user_obj = get_user_object(request.user.username)
    all_sites = phantom_get_sites(request.GET, user_obj)
    if site in all_sites:
        response_dict = {
            "id": site,
            "credentials": "/api/dev/credentials/%s" % site,
            "uri": "/api/dev/sites/%s" % site
        }
        h = HttpResponse(json.dumps(response_dict), mimetype='application/javascript')
    else:
        h = HttpResponseNotFound('Site %s not found' % site, mimetype='application/javascript')
    return h


@basic_http_auth
@require_http_methods(["GET", "POST"])
def credentials(request):
    user_obj = get_user_object(request.user.username)

    if request.method == "GET":
        all_clouds = user_obj.get_clouds()
        response_list = []
        for cloud in all_clouds.values():
            credentials_name = cloud.cloudname
            credentials_dict = {
                "id": credentials_name,
                "access_key": cloud.iaas_key,
                "secret_key": cloud.iaas_secret,
                "key_name": cloud.keyname,
                "uri": "/api/dev/credentials/%s" % credentials_name
            }
            response_list.append(credentials_dict)
        h = HttpResponse(json.dumps(response_list), mimetype='application/javascript')
    elif request.method == "POST":
        try:
            content = json.loads(request.body)
        except:
            return HttpResponseBadRequest()

        required_params = ["id", "access_key", "secret_key", "key_name"]
        if not has_all_required_params(required_params, content):
            return HttpResponseBadRequest()

        site = content["id"]
        access_key = content["access_key"]
        secret_key = content["secret_key"]
        key_name = content["key_name"]

        # Check that the site exists
        all_sites = phantom_get_sites(request.POST, user_obj)
        if site not in all_sites:
            return HttpResponseBadRequest()

        response_dict = {
            "id": site,
            "access_key": access_key,
            "secret_key": secret_key,
            "key_name": key_name,
            "uri": "/api/dev/credentials/%s" % site
        }

        # Add credentials to DTRS
        try:
            user_obj.add_site(site, access_key, secret_key, key_name)
        except:
            log.exception("Failed to add credentials for site %s" % site)
            return HttpResponseServerError()

        h = HttpResponse(json.dumps(response_dict), status=201, mimetype='application/javascript')

    return h


@basic_http_auth
@require_http_methods(["GET", "PUT", "DELETE"])
def credentials_resource(request, site):
    user_obj = get_user_object(request.user.username)

    if request.method == "GET":
        all_clouds = user_obj.get_clouds()
        cloud = all_clouds.get(site)

        if cloud is not None:
            response_dict = {
                "id": cloud.cloudname,
                "access_key": cloud.iaas_key,
                "secret_key": cloud.iaas_secret,
                "key_name": cloud.keyname,
                "uri": "/api/dev/credentials/%s" % cloud.cloudname
            }
            h = HttpResponse(json.dumps(response_dict), mimetype='application/javascript')
        else:
            h = HttpResponseNotFound('Credentials for site %s not found' % site, mimetype='application/javascript')
    elif request.method == "PUT":
        try:
            content = json.loads(request.body)
        except:
            return HttpResponseBadRequest()

        required_params = ["id", "access_key", "secret_key", "key_name"]
        if not has_all_required_params(required_params, content):
            return HttpResponseBadRequest()

        if site != content["id"]:
            return HttpResponseBadRequest()

        access_key = content["access_key"]
        secret_key = content["secret_key"]
        key_name = content["key_name"]

        # Check that the site exists
        all_sites = phantom_get_sites(request.REQUEST, user_obj)
        if site not in all_sites:
            return HttpResponseBadRequest()

        # Check that credentials exist
        if site not in user_obj.get_clouds():
            return HttpResponseBadRequest()

        response_dict = {
            "id": site,
            "access_key": access_key,
            "secret_key": secret_key,
            "key_name": key_name,
            "uri": "/api/dev/credentials/%s" % site
        }

        # Add credentials to DTRS
        try:
            user_obj.add_site(site, access_key, secret_key, key_name)
        except:
            log.exception("Failed to add credentials for site %s" % site)
            return HttpResponseServerError()

        h = HttpResponse(json.dumps(response_dict), status=201, mimetype='application/javascript')
    elif request.method == "DELETE":
        # Check that credentials exist
        if site not in user_obj.get_clouds():
            return HttpResponseBadRequest()

        # Remove credentials from DTRS
        try:
            user_obj.delete_site(site)
        except:
            log.exception("Failed to remove credentials for site %s" % site)
            return HttpResponseServerError()

        h = HttpResponse(status=204)

    return h


@basic_http_auth
@require_http_methods(["GET", "POST"])
def launchconfigurations(request):
    if request.method == "GET":
        all_launch_configurations = get_all_launch_configurations(request.user.username)
        response_list = []
        for lc in all_launch_configurations:
            lc_dict = {
                "id": lc.id,
                "name": lc.name,
                "owner": lc.username,
                "uri": "/api/dev/launchconfigurations/%s" % lc.id,
                "cloud_params": {}
            }

            user_obj = get_user_object(lc.username)
            dt = user_obj.get_dt(lc.name)

            host_max_pairs = lc.hostmaxpairdb_set.all()
            for hmp in host_max_pairs:
                cloud = hmp.cloud_name
                mapping = dt["mappings"][cloud]
                lc_dict["cloud_params"][cloud] = {
                    "max_vms": hmp.max_vms,
                    "common": hmp.common_image,
                    "rank": hmp.rank,
                    "image_id": mapping["iaas_image"],
                    "instance_type": mapping["iaas_allocation"],
                    "user_data": dt["contextualization"].get("userdata")
                }
            response_list.append(lc_dict)

        h = HttpResponse(json.dumps(response_list), mimetype='application/javascript')
    elif request.method == "POST":
        #try:
            #content = json.loads(request.body)
        #except:
            #return HttpResponseBadRequest()

        #required_params = ["id", "access_key", "secret_key", "key_name"]
        #if not has_all_required_params(required_params, content):
            #return HttpResponseBadRequest()

        #site = content["id"]
        #access_key = content["access_key"]
        #secret_key = content["secret_key"]
        #key_name = content["key_name"]

        ## Check that the site exists
        #all_sites = phantom_get_sites(request.POST, user_obj)
        #if site not in all_sites:
            #return HttpResponseBadRequest()

        #response_dict = {
            #"id": site,
            #"access_key": access_key,
            #"secret_key": secret_key,
            #"key_name": key_name,
            #"uri": "/api/dev/credentials/%s" % site
        #}

        ## Add credentials to DTRS
        #try:
            #user_obj.add_site(site, access_key, secret_key, key_name)
        #except:
            #log.exception("Failed to add credentials for site %s" % site)
            #return HttpResponseServerError()

        #h = HttpResponse(json.dumps(response_dict), status=201, mimetype='application/javascript')
        h = HttpResponse(status=201)

    return h


@basic_http_auth
@require_http_methods(["GET", "PUT", "DELETE"])
def launchconfiguration_resource(request, id):
    if request.method == "GET":
        lc = get_launch_configuration(id)
        if lc is not None and lc.username == request.user.username:
            response_dict = {
                "id": lc.id,
                "name": lc.name,
                "owner": lc.username,
                "uri": "/api/dev/launchconfigurations/%s" % lc.id,
                "cloud_params": {}
            }

            user_obj = get_user_object(lc.username)
            dt = user_obj.get_dt(lc.name)

            host_max_pairs = lc.hostmaxpairdb_set.all()
            for hmp in host_max_pairs:
                cloud = hmp.cloud_name
                mapping = dt["mappings"][cloud]
                response_dict["cloud_params"][cloud] = {
                    "max_vms": hmp.max_vms,
                    "common": hmp.common_image,
                    "rank": hmp.rank,
                    "image_id": mapping["iaas_image"],
                    "instance_type": mapping["iaas_allocation"],
                    "user_data": dt["contextualization"].get("userdata")
                }
            h = HttpResponse(json.dumps(response_dict), mimetype='application/javascript')
        else:
            h = HttpResponseNotFound('Launch configuration %s not found' % id, mimetype='application/javascript')
        return h
    elif request.method == "PUT":
        pass
    elif request.method == "DELETE":
        lc = get_launch_configuration(id)
        if lc is not None and lc.username == request.user.username:
            delete_launch_configuration(lc)
            h = HttpResponse(status=204)
        else:
            h = HttpResponseNotFound('Launch configuration %s not found' % id, mimetype='application/javascript')